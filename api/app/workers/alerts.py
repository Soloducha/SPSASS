"""Evaluación de reglas de alerta contra métricas.

El worker arq ejecuta ``evaluate_alerts`` cada minuto. La función carga todas
las reglas activas, resuelve sus targets (servidores), lee métricas en la
ventana de duración y evalúa la condición sostenida (todos los samples en la
ventana deben cumplir el umbral).

Idempotencia: no se re-dispara mientras exista una alerta OPEN/ACKNOWLEDGED para
la misma regla+servidor. Cuando la condición deja de cumplirse, la alerta se
marca RESOLVED.

Solo se evalúan reglas de EntityType.SERVER en este slice; otros tipos se
loguean en debug y se saltan.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.alert import Alert, AlertDelivery, AlertOperator, AlertRule, AlertStatus, EntityType
from app.models.metric import Metric, MetricType
from app.models.server import Server

if TYPE_CHECKING:
    from uuid import UUID


@dataclass(frozen=True, slots=True)
class _EvalContext:
    """Contexto de evaluación para _evaluate_rule_for_server."""
    session: AsyncSession
    rule: AlertRule
    server_id: "UUID"
    metric_type: MetricType
    window_start: datetime
    now: datetime


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


async def _evaluate_rule_for_server(ctx: _EvalContext) -> bool:
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

    # Buscar alerta activa existente
    active_alert = await session.scalar(
        select(Alert).where(
            Alert.rule_id == rule.id,
            Alert.server_id == server_id,
            Alert.status.in_([AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED]),
        )
    )

    if cond_ok:
        if active_alert is None:
            # Crear nueva alerta
            alert = Alert(
                rule_id=rule.id,
                server_id=server_id,
                tenant_id=rule.tenant_id,
                severity=rule.severity,
                status=AlertStatus.OPEN,
                message=_describe_condition(rule),
                triggered_at=now,
                value_at_trigger=values[-1],
            )
            session.add(alert)
            await session.flush()

            # Crear AlertDelivery pendientes por cada canal (keys de dict)
            channels = rule.channels or {}
            for channel in sorted(set(channels.keys())):
                delivery = AlertDelivery(
                    alert_id=alert.id,
                    channel=channel,
                    status="pending",
                    tenant_id=rule.tenant_id,
                )
                session.add(delivery)

            logger.info(
                "alert_created",
                alert_id=str(alert.id),
                rule_id=str(rule.id),
                server_id=str(server_id),
                tenant_id=str(rule.tenant_id),
                severity=rule.severity.value,
                value=values[-1],
            )
            return True
        logger.debug("alert_already_open", alert_id=str(active_alert.id), rule_id=str(rule.id))
    elif active_alert is not None:
        # cond_ok == False y hay alerta activa → resolver
        active_alert.status = AlertStatus.RESOLVED
        active_alert.resolved_at = now
        logger.info(
            "alert_resolved",
            alert_id=str(active_alert.id),
            rule_id=str(rule.id),
            server_id=str(server_id),
            tenant_id=str(rule.tenant_id),
        )
    return False


async def evaluate_alerts(session: AsyncSession) -> int:
    """Evalúa todas las reglas de alerta activas contra métricas recientes.

    Para cada regla SERVER:
      - Resuelve targets (entity_id específico o todos los servidores del tenant).
      - Lee métricas en ventana [now - duration_s, now].
      - Condición sostenida: TODOS los samples deben cumplir el umbral.
      - Si cond_ok y no hay alerta OPEN/ACK → crea alerta + deliveries pending.
      - Si !cond_ok y hay alerta OPEN/ACK → resuelve alerta.

    Devuelve el número de alertas NUEVAS creadas en esta ejecución.
    """
    created = 0
    now = datetime.now(UTC)

    # 1. Cargar todas las reglas activas (todos los tenants, sin RLS)
    rules = (await session.scalars(select(AlertRule).where(AlertRule.is_active.is_(True)))).all()

    for rule in rules:
        # 2. Solo SERVER en este slice
        if rule.entity_type != EntityType.SERVER:
            logger.debug("rule_skipped_non_server", rule_id=str(rule.id), entity_type=rule.entity_type.value)
            continue

        # 3. Resolver targets
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
            continue

        # 4. Parsear metric type
        try:
            metric_type = MetricType(rule.metric)
        except ValueError:
            logger.warning("rule_invalid_metric", rule_id=str(rule.id), metric=rule.metric)
            continue

        # 5. Ventana de evaluación
        window_start = now - timedelta(seconds=rule.duration_s)

        for server_id in target_server_ids:
            ctx = _EvalContext(
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

    await session.commit()
    return created
