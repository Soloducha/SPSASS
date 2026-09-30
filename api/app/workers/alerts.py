"""Evaluación de reglas de alerta contra métricas y estado de entidades.

El worker arq ejecuta ``evaluate_alerts`` cada minuto. La función carga todas
las reglas activas, resuelve sus targets según el entity_type, evalúa la
condición y crea/resuelve alertas.

Idempotencia: no se re-dispara mientras exista una alerta OPEN/ACKNOWLEDGED para
la misma regla + target_entity_id. Cuando la condición deja de cumplirse, la
alerta se marca RESOLVED.

Soporta EntityType: SERVER, SERVICE, PROCESS, JOB.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.alert import Alert, AlertDelivery, AlertOperator, AlertRule, AlertStatus, EntityType
from app.models.job import Job, JobRun
from app.models.metric import Metric, MetricType
from app.models.process import Process
from app.models.server import Server
from app.models.service import Service, ServiceState

if TYPE_CHECKING:
    from uuid import UUID


@dataclass(frozen=True, slots=True)
class _EvalContext:
    """Contexto de evaluación base."""
    session: AsyncSession
    rule: AlertRule
    now: datetime


@dataclass(frozen=True, slots=True)
class _ServerEvalContext(_EvalContext):
    """Contexto para evaluación SERVER."""
    server_id: "UUID"
    metric_type: MetricType
    window_start: datetime


logger = get_logger(__name__)


def _matches(operator: AlertOperator, value: float, threshold: float) -> bool:
    """Evalúa si ``value`` cumple la condición contra ``threshold``."""
    ops = {
        AlertOperator.GT: lambda v, t: v > t,
        AlertOperator.GTE: lambda v, t: v >= t,
        AlertOperator.LT: lambda v, t: v < t,
        AlertOperator.LTE: lambda v, t: v <= t,
        AlertOperator.EQ: lambda v, t: v == t,
        AlertOperator.NEQ: lambda v, t: v != t,
    }
    func = ops.get(operator)
    return func(value, threshold) if func else False


def _describe_condition(rule: AlertRule) -> str:
    """Genera descripción humana concisa de la condición de la regla."""
    metric_name = rule.metric
    op_map = {
        AlertOperator.GT: ">",
        AlertOperator.GTE: ">=",
        AlertOperator.LT: "<",
        AlertOperator.LTE: "<=",
        AlertOperator.EQ: "==",
        AlertOperator.NEQ: "!=",
    }
    op_str = op_map.get(rule.operator, "?")
    return f"{metric_name} {op_str} {rule.threshold} sustained >= {rule.duration_s}s"


async def _get_active_alert(
    session: AsyncSession,
    rule_id: "UUID",
    target_entity_id: "UUID | None",
    server_id: "UUID | None" = None,
) -> Alert | None:
    """Busca una alerta activa (OPEN/ACKNOWLEDGED) para una regla + target.

    Para SERVER: usa server_id + rule_id.
    Para SERVICE/PROCESS/JOB: usa target_entity_id + rule_id (server_id puede ser None).
    """
    if target_entity_id is not None:
        return await session.scalar(  # type: ignore[no-any-return]
            select(Alert).where(
                Alert.rule_id == rule_id,
                Alert.target_entity_id == target_entity_id,
                Alert.status.in_([AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED]),
            )
        )
    # Fallback para compatibilidad con alertas antiguas (SERVER sin target_entity_id)
    return await session.scalar(  # type: ignore[no-any-return]
        select(Alert).where(
            Alert.rule_id == rule_id,
            Alert.server_id == server_id,
            Alert.status.in_([AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED]),
        )
    )


@dataclass(frozen=True, slots=True)
class _AlertCreateParams:
    """Parámetros para crear alerta + deliveries."""
    session: AsyncSession
    rule: AlertRule
    tenant_id: "UUID"
    message: str
    value_at_trigger: float
    now: datetime
    server_id: "UUID | None" = None
    target_entity_id: "UUID | None" = None


async def _create_alert_and_deliveries(params: _AlertCreateParams) -> Alert:
    """Crea una alerta y sus deliveries pendientes."""
    alert = Alert(
        rule_id=params.rule.id,
        server_id=params.server_id,
        target_entity_id=params.target_entity_id,
        tenant_id=params.tenant_id,
        severity=params.rule.severity,
        status=AlertStatus.OPEN,
        message=params.message,
        triggered_at=params.now,
        value_at_trigger=params.value_at_trigger,
    )
    params.session.add(alert)
    await params.session.flush()

    # Crear AlertDelivery pendientes por cada canal (keys de dict)
    channels = params.rule.channels or {}
    for channel in sorted(set(channels.keys())):
        delivery = AlertDelivery(
            alert_id=alert.id,
            channel=channel,
            status="pending",
            tenant_id=params.tenant_id,
            config=channels.get(channel),
        )
        params.session.add(delivery)

    logger.info(
        "alert_created",
        alert_id=str(alert.id),
        rule_id=str(params.rule.id),
        server_id=str(params.server_id) if params.server_id else None,
        target_entity_id=str(params.target_entity_id) if params.target_entity_id else None,
        tenant_id=str(params.tenant_id),
        severity=params.rule.severity.value,
        value=params.value_at_trigger,
    )
    return alert


async def _resolve_alert(alert: Alert, now: datetime, rule_id: "UUID") -> None:
    """Marca una alerta como RESOLVED."""
    alert.status = AlertStatus.RESOLVED
    alert.resolved_at = now
    logger.info(
        "alert_resolved",
        alert_id=str(alert.id),
        rule_id=str(rule_id),
        tenant_id=str(alert.tenant_id),
    )


# ──────────────────────────────────────────────
# Evaluación SERVER (existente, sin cambios de comportamiento)
# ──────────────────────────────────────────────

async def _evaluate_rule_for_server(ctx: _ServerEvalContext) -> bool:
    """Evalúa una regla para un servidor. Devuelve True si se creó alerta nueva."""
    session = ctx.session
    rule = ctx.rule
    server_id = ctx.server_id
    metric_type = ctx.metric_type
    window_start = ctx.window_start
    now = ctx.now

    # Fetch samples en ventana
    values_result = await session.scalars(
        select(Metric.value).where(
            Metric.tenant_id == rule.tenant_id,
            Metric.server_id == server_id,
            Metric.type == metric_type,
            Metric.ts >= window_start,
        )
    )
    values = values_result.all()

    if not values:
        return False

    # Condición sostenida: TODOS los samples deben cumplir
    cond_ok = all(_matches(rule.operator, value, rule.threshold) for value in values)

    # Buscar alerta activa existente (por server_id para compatibilidad)
    active_alert = await _get_active_alert(session, rule.id, None, server_id)

    if cond_ok:
        if active_alert is None:
            await _create_alert_and_deliveries(_AlertCreateParams(
                session=session,
                rule=rule,
                tenant_id=rule.tenant_id,
                message=_describe_condition(rule),
                value_at_trigger=values[-1],
                now=now,
                server_id=server_id,
                target_entity_id=server_id,  # Para SERVER, target_entity_id = server_id
            ))
            return True
        logger.debug("alert_already_open", alert_id=str(active_alert.id), rule_id=str(rule.id))
    elif active_alert is not None:
        await _resolve_alert(active_alert, now, rule.id)
    return False


# ──────────────────────────────────────────────
# Evaluación SERVICE
# ──────────────────────────────────────────────

async def _evaluate_rule_for_service(
    session: AsyncSession,
    rule: AlertRule,
    service: Service,
    now: datetime,
) -> bool:
    """Evalúa una regla SERVICE para un servicio específico.

    Un servicio está en violación cuando last_status != desired_state.
    Si last_status es None/UNKNOWN (nunca ingerido), NO dispara.
    """
    # Si nunca se ha ingerido estado, no evaluamos (unknown no es violación)
    if service.last_status == ServiceState.UNKNOWN:
        return False

    # Violación: estado reportado != desired_state
    is_violating = service.last_status != service.desired_state

    # Buscar alerta activa existente por target_entity_id (service.id)
    active_alert = await _get_active_alert(session, rule.id, service.id)

    if is_violating:
        if active_alert is None:
            await _create_alert_and_deliveries(_AlertCreateParams(
                session=session,
                rule=rule,
                tenant_id=rule.tenant_id,
                message=f"Service '{service.name}' status is {service.last_status.value}, desired is {service.desired_state.value}",
                value_at_trigger=1.0,  # valor binario: 1 = violating
                now=now,
                server_id=service.server_id,
                target_entity_id=service.id,
            ))
            return True
        logger.debug("alert_already_open", alert_id=str(active_alert.id), rule_id=str(rule.id), service_id=str(service.id))
    elif active_alert is not None:
        await _resolve_alert(active_alert, now, rule.id)
    return False


# ──────────────────────────────────────────────
# Evaluación PROCESS
# ──────────────────────────────────────────────

async def _evaluate_rule_for_process(
    session: AsyncSession,
    rule: AlertRule,
    process: Process,
    now: datetime,
) -> bool:
    """Evalúa una regla PROCESS para un proceso específico.

    Un proceso está en violación cuando last_count < expected_count.
    Si last_checked_at es None (nunca ingerido), NO dispara.
    """
    # Si nunca se ha ingerido, no evaluamos
    if process.last_checked_at is None:
        return False

    # Violación: count reportado < expected_count
    is_violating = process.last_count < process.expected_count

    # Buscar alerta activa existente por target_entity_id (process.id)
    active_alert = await _get_active_alert(session, rule.id, process.id)

    if is_violating:
        if active_alert is None:
            await _create_alert_and_deliveries(_AlertCreateParams(
                session=session,
                rule=rule,
                tenant_id=rule.tenant_id,
                message=f"Process '{process.name}' count is {process.last_count}, expected >= {process.expected_count}",
                value_at_trigger=float(process.last_count),
                now=now,
                server_id=process.server_id,
                target_entity_id=process.id,
            ))
            return True
        logger.debug("alert_already_open", alert_id=str(active_alert.id), rule_id=str(rule.id), process_id=str(process.id))
    elif active_alert is not None:
        await _resolve_alert(active_alert, now, rule.id)
    return False


# ──────────────────────────────────────────────
# Evaluación JOB
# ──────────────────────────────────────────────

async def _evaluate_rule_for_job(
    session: AsyncSession,
    rule: AlertRule,
    job: Job,
    now: datetime,
) -> bool:
    """Evalúa una regla JOB para un job específico.

    Un job está en violación cuando su JobRun más reciente (dentro de la ventana
    de rule.duration_s segundos) tiene status en {"failed", "timeout"} Y no fue
    ya alertado por el runner (run_metadata["alerted"] == True).

    Resolución: la alerta se resuelve cuando:
    - El JobRun más reciente en la ventana es "success", O
    - El JobRun más reciente es fallo/timeout que YA fue alertado por el runner, O
    - No hay fallo en la ventana.
    """
    window_start = now - timedelta(seconds=rule.duration_s)

    # Buscar el JobRun más reciente en la ventana
    latest_run = await session.scalar(
        select(JobRun)
        .where(
            JobRun.job_id == job.id,
            JobRun.started_at >= window_start,
        )
        .order_by(JobRun.started_at.desc())
        .limit(1)
    )

    if latest_run is None:
        # No hay runs en la ventana → no hay violación, resolver si hay alerta abierta
        active_alert = await _get_active_alert(session, rule.id, job.id)
        if active_alert is not None:
            await _resolve_alert(active_alert, now, rule.id)
        return False

    # Verificar si el run ya fue alertado por el runner (idempotencia)
    run_alerted_by_runner = latest_run.run_metadata.get("alerted", False) if latest_run.run_metadata else False
    is_failing = latest_run.status in ("failed", "timeout")

    # Violación: run fallido/timeout Y no alertado por runner
    is_violating = is_failing and not run_alerted_by_runner

    active_alert = await _get_active_alert(session, rule.id, job.id)

    if is_violating:
        if active_alert is None:
            msg = (
                f"Job '{job.name}' timed out after {job.timeout_s}s"
                if latest_run.status == "timeout"
                else f"Job '{job.name}' failed (exit={latest_run.exit_code})"
            )
            await _create_alert_and_deliveries(_AlertCreateParams(
                session=session,
                rule=rule,
                tenant_id=rule.tenant_id,
                message=msg,
                value_at_trigger=float(latest_run.exit_code or 0.0),
                now=now,
                server_id=job.server_id,
                target_entity_id=job.id,
            ))
            return True
        logger.debug("alert_already_open", alert_id=str(active_alert.id), rule_id=str(rule.id), job_id=str(job.id))
    elif active_alert is not None:
        # Resolver si: run es success, O run es fallo ya alertado por runner, O no hay fallo
        should_resolve = (
            latest_run.status == "success"
            or (is_failing and run_alerted_by_runner)
            or not is_failing
        )
        if should_resolve:
            await _resolve_alert(active_alert, now, rule.id)
    return False


# ──────────────────────────────────────────────
# Función principal
# ──────────────────────────────────────────────

async def evaluate_alerts(session: AsyncSession) -> int:
    """Evalúa todas las reglas de alerta activas contra métricas/estado reciente.

    Para cada regla según entity_type:
      - SERVER: métricas en ventana [now - duration_s, now], condición sostenida (ALL samples).
      - SERVICE: desired_state vs last_status (si last_status != UNKNOWN).
      - PROCESS: expected_count vs last_count (si last_checked_at no es None).
      - JOB: JobRun más reciente en ventana duration_s con status failed/timeout no alertado por runner.

    Devuelve el número de alertas NUEVAS creadas en esta ejecución.
    """
    created = 0
    now = datetime.now(UTC)

    # 1. Cargar todas las reglas activas (todos los tenants, sin RLS)
    rules = (await session.scalars(select(AlertRule).where(AlertRule.is_active.is_(True)))).all()

    for rule in rules:
        try:
            if rule.entity_type == EntityType.SERVER:
                created += await _evaluate_server_rules(session, rule, now)
            elif rule.entity_type == EntityType.SERVICE:
                created += await _evaluate_service_rules(session, rule, now)
            elif rule.entity_type == EntityType.PROCESS:
                created += await _evaluate_process_rules(session, rule, now)
            elif rule.entity_type == EntityType.JOB:
                created += await _evaluate_job_rules(session, rule, now)
            else:
                logger.debug("rule_skipped_unknown_entity", rule_id=str(rule.id), entity_type=rule.entity_type.value)
        except Exception as e:
            # Log y continuar con la siguiente regla (no crashea el worker completo)
            logger.warning(
                "rule_evaluation_error",
                rule_id=str(rule.id),
                entity_type=rule.entity_type.value,
                error=str(e),
            )

    await session.commit()
    return created


async def _evaluate_server_rules(session: AsyncSession, rule: AlertRule, now: datetime) -> int:
    """Evalúa regla SERVER contra todos los targets."""
    created = 0

    # Resolver targets
    if rule.entity_id is not None:
        target_server_ids = [rule.entity_id]
    else:
        target_server_ids = list(
            await session.scalars(
                select(Server.id).where(Server.tenant_id == rule.tenant_id)
            )
        )

    if not target_server_ids:
        logger.debug("rule_no_targets", rule_id=str(rule.id), tenant_id=str(rule.tenant_id))
        return 0

    # Parsear metric type
    try:
        metric_type = MetricType(rule.metric)
    except ValueError:
        logger.warning("rule_invalid_metric", rule_id=str(rule.id), metric=rule.metric)
        return 0

    # Ventana de evaluación
    window_start = now - timedelta(seconds=rule.duration_s)

    for server_id in target_server_ids:
        ctx = _ServerEvalContext(
            session=session,
            rule=rule,
            server_id=server_id,
            metric_type=metric_type,
            window_start=window_start,
            now=now,
        )
        alert_created = await _evaluate_rule_for_server(ctx)
        if alert_created:
            created += 1

    return created


async def _evaluate_service_rules(session: AsyncSession, rule: AlertRule, now: datetime) -> int:
    """Evalúa regla SERVICE contra todos los targets."""
    created = 0

    # Resolver targets
    if rule.entity_id is not None:
        target_services = await _get_services_for_rule(session, rule)
    else:
        target_services = list(
            await session.scalars(
                select(Service).where(Service.tenant_id == rule.tenant_id)
            )
        )

    if not target_services:
        logger.debug("rule_no_targets", rule_id=str(rule.id), tenant_id=str(rule.tenant_id))
        return 0

    for service in target_services:
        alert_created = await _evaluate_rule_for_service(session, rule, service, now)
        if alert_created:
            created += 1

    return created


async def _evaluate_process_rules(session: AsyncSession, rule: AlertRule, now: datetime) -> int:
    """Evalúa regla PROCESS contra todos los targets."""
    created = 0

    # Resolver targets
    if rule.entity_id is not None:
        target_processes = await _get_processes_for_rule(session, rule)
    else:
        target_processes = list(
            await session.scalars(
                select(Process).where(Process.tenant_id == rule.tenant_id)
            )
        )

    if not target_processes:
        logger.debug("rule_no_targets", rule_id=str(rule.id), tenant_id=str(rule.tenant_id))
        return 0

    for process in target_processes:
        alert_created = await _evaluate_rule_for_process(session, rule, process, now)
        if alert_created:
            created += 1

    return created


async def _evaluate_job_rules(session: AsyncSession, rule: AlertRule, now: datetime) -> int:
    """Evalúa regla JOB contra todos los targets."""
    created = 0

    # Resolver targets
    if rule.entity_id is not None:
        target_jobs = await _get_jobs_for_rule(session, rule)
    else:
        target_jobs = list(
            await session.scalars(
                select(Job).where(Job.tenant_id == rule.tenant_id)
            )
        )

    if not target_jobs:
        logger.debug("rule_no_targets", rule_id=str(rule.id), tenant_id=str(rule.tenant_id))
        return 0

    for job in target_jobs:
        alert_created = await _evaluate_rule_for_job(session, rule, job, now)
        if alert_created:
            created += 1

    return created


async def _get_services_for_rule(session: AsyncSession, rule: AlertRule) -> list[Service]:
    """Obtiene servicios para una regla, validando tenant y existencia."""
    if rule.entity_id is None:
        return []

    service = await session.get(Service, rule.entity_id)
    if service is None:
        logger.debug("rule_target_not_found", rule_id=str(rule.id), entity_id=str(rule.entity_id), entity_type="service")
        return []
    if service.tenant_id != rule.tenant_id:
        logger.debug("rule_target_cross_tenant", rule_id=str(rule.id), entity_id=str(rule.entity_id), entity_type="service")
        return []
    return [service]


async def _get_processes_for_rule(session: AsyncSession, rule: AlertRule) -> list[Process]:
    """Obtiene procesos para una regla, validando tenant y existencia."""
    if rule.entity_id is None:
        return []

    process = await session.get(Process, rule.entity_id)
    if process is None:
        logger.debug("rule_target_not_found", rule_id=str(rule.id), entity_id=str(rule.entity_id), entity_type="process")
        return []
    if process.tenant_id != rule.tenant_id:
        logger.debug("rule_target_cross_tenant", rule_id=str(rule.id), entity_id=str(rule.entity_id), entity_type="process")
        return []
    return [process]


async def _get_jobs_for_rule(session: AsyncSession, rule: AlertRule) -> list[Job]:
    """Obtiene jobs para una regla, validando tenant y existencia."""
    if rule.entity_id is None:
        return []

    job = await session.get(Job, rule.entity_id)
    if job is None:
        logger.debug("rule_target_not_found", rule_id=str(rule.id), entity_id=str(rule.entity_id), entity_type="job")
        return []
    if job.tenant_id != rule.tenant_id:
        logger.debug("rule_target_cross_tenant", rule_id=str(rule.id), entity_id=str(rule.entity_id), entity_type="job")
        return []
    return [job]
