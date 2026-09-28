"""Worker de ejecución de jobs programados (CRON).

Este worker corre centralizado en el contenedor arq y ejecuta los jobs
definidos en BD cuyo `schedule_cron` es debido. El `server_id` del job
es solo contexto de referencia, NO un target de ejecución remota.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from croniter import croniter
from sqlalchemy import select

from app.core.logging import get_logger
from app.models.alert import Alert, AlertSeverity
from app.models.job import Job, JobKind, JobRun, JobStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

# ──────────────────────────────────────────────
# Configuración
# ──────────────────────────────────────────────

OUTPUT_TAIL_MAX_CHARS = 4000
PROCESS_KILL_GRACE_SECONDS = 5


@dataclass(frozen=True, slots=True)
class _JobRunResult:
    """Resultado de ejecutar un job."""
    job: Job
    run: JobRun
    alert_created: bool


def _is_cron_due(expr: str, now: datetime) -> bool:
    """Determina si un job cron es debido AHORA.

    Estrategia: comparamos el siguiente tiempo de ejecución *previo* al minuto
    actual. Si el job debió ejecutarse en o antes del minuto actual (redondeado
    al minuto), lo ejecutamos. Esto garantiza que se dispare exactamente una vez
    por minuto debido cuando el worker corre cada minuto.

    Equivalente a: ``croniter(expr, now - 1min).get_next(datetime) <= now``
    pero más explícito para depuración.
    """
    try:
        base = now - timedelta(minutes=1)
        itr = croniter(expr, base)
        next_run: datetime = itr.get_next(datetime)  # croniter returns Any, but we expect datetime
        is_due = next_run <= now
    except Exception as e:
        logger.warning("croniter_parse_error", expr=expr, error=str(e))
        return False
    return is_due


async def _run_job_command(
    command: str,
    timeout_s: int,
) -> tuple[int | None, str, bool]:
    """Ejecuta un comando con timeout.

    Returns:
        (exit_code, output_tail, timed_out)
        - exit_code: None si timeout, int si completó
        - output_tail: últimos OUTPUT_TAIL_MAX_CHARS chars de stdout/stderr
        - timed_out: True si el proceso fue matado por timeout
    """
    # Usar create_subprocess_shell para soportar comandos con pipes, redirecciones, etc.
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=None,
    )

    timed_out = False
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        exit_code = proc.returncode
    except TimeoutError:
        # Matar el proceso: terminate -> wait -> kill
        timed_out = True
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=PROCESS_KILL_GRACE_SECONDS)
        except (TimeoutError, ProcessLookupError):
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
        exit_code = None
        stdout = None

    output = stdout.decode("utf-8", errors="replace") if stdout else ""
    output_tail = output[-OUTPUT_TAIL_MAX_CHARS:] if output else ""
    return exit_code, output_tail, timed_out


def _create_failure_alert(
    session: AsyncSession,
    job: Job,
    run: JobRun,
    message: str,
    severity: AlertSeverity = AlertSeverity.CRITICAL,
) -> Alert | None:
    """Crea una alerta por fallo de job y sus deliveries pendientes.

    NOTA: Alert.rule_id es NOT NULL en el modelo, pero los fallos de job
    no derivan de una AlertRule. Como workaround, creamos la alerta sin
    rule_id (lo cual fallaría en DB) — el modelo actual NO permite rule_id
    nulo. Revisar migración futura si se quiere separar alertas de job.
    Por ahora, NO creamos alerta si rule_id es requerido y no hay regla.
    """
    # Dado que Alert.rule_id es NOT NULL, no podemos crear alerta directa
    # sin una regla asociada. Esta limitación del modelo se documenta aquí.
    # Para T2, logueamos el intento y saltamos la creación de alerta.
    logger.warning(
        "job_failure_alert_skipped_no_rule",
        job_id=str(job.id),
        job_name=job.name,
        run_id=str(run.id),
        tenant_id=str(job.tenant_id),
        message=message,
    )
    # Retornamos None para indicar que no se creó alerta
    # (El caller debe manejar esto)
    return None


async def _process_job(session: AsyncSession, job: Job, now: datetime) -> _JobRunResult | None:
    """Procesa un job CRON individual si es debido.

    Returns:
        _JobRunResult si se ejecutó, None si se saltó.
    """
    if not job.schedule_cron:
        logger.debug("job_skipped_no_cron", job_id=str(job.id), job_name=job.name)
        return None

    # Validar expresión cron
    try:
        croniter(job.schedule_cron, now)
    except Exception as e:
        logger.warning("job_invalid_cron", job_id=str(job.id), job_name=job.name, expr=job.schedule_cron, error=str(e))
        return None

    # Verificar si es debido
    if not _is_cron_due(job.schedule_cron, now):
        logger.debug("job_not_due", job_id=str(job.id), job_name=job.name, cron=job.schedule_cron)
        return None

    # Guard contra ejecuciones concurrentes: si la última run está "running", saltar
    latest_run = await session.scalar(
        select(JobRun)
        .where(JobRun.job_id == job.id)
        .order_by(JobRun.started_at.desc())
        .limit(1)
    )
    if latest_run and latest_run.status == "running":
        logger.debug("job_skipped_previous_running", job_id=str(job.id), job_name=job.name, run_id=str(latest_run.id))
        return None

    # Crear JobRun inicial con status="running"
    run = JobRun(
        job_id=job.id,
        tenant_id=job.tenant_id,
        started_at=now,
        status="running",
        exit_code=None,
        output_tail=None,
        run_metadata={},
    )
    session.add(run)
    await session.flush()

    logger.info("job_run_started", job_id=str(job.id), job_name=job.name, run_id=str(run.id))

    # Ejecutar comando
    exit_code, output_tail, timed_out = await _run_job_command(job.command, job.timeout_s)

    finished_at = datetime.now(UTC)

    # Actualizar JobRun con resultado
    run.finished_at = finished_at
    run.exit_code = exit_code
    run.output_tail = output_tail
    if timed_out:
        run.status = "timeout"
        run.run_metadata = {"timed_out": True}
        logger.warning(
            "job_run_timed_out",
            job_id=str(job.id),
            job_name=job.name,
            run_id=str(run.id),
            timeout_s=job.timeout_s,
        )
    elif exit_code == 0:
        run.status = "success"
    else:
        run.status = "failed"
        logger.warning(
            "job_run_failed",
            job_id=str(job.id),
            job_name=job.name,
            run_id=str(run.id),
            exit_code=exit_code,
        )

    alert_created = False

    # Crear alerta si fallo y alert_on_fail
    if run.status in ("failed", "timeout") and job.alert_on_fail:
        # NOTA: Alert.rule_id es NOT NULL, no podemos crear alerta directa
        # sin una regla. Ver _create_failure_alert para detalles.
        # Por ahora solo logueamos.
        logger.warning(
            "job_failure_alert_not_created_rule_id_required",
            job_id=str(job.id),
            job_name=job.name,
            run_id=str(run.id),
            tenant_id=str(job.tenant_id),
            status=run.status,
            exit_code=exit_code,
        )
        alert_created = False

    await session.flush()
    logger.info(
        "job_run_completed",
        job_id=str(job.id),
        job_name=job.name,
        run_id=str(run.id),
        status=run.status,
        exit_code=exit_code,
        timed_out=timed_out,
        alert_created=alert_created,
    )

    return _JobRunResult(job=job, run=run, alert_created=alert_created)


async def run_due_jobs(session: AsyncSession) -> int:
    """Ejecuta todos los jobs CRON activos cuyo schedule_cron es debido.

    Se ejecuta sin contexto de tenant (usa get_db_session_without_tenant),
    igual que evaluate_alerts: procesa TODOS los tenants en un solo pase.

    Returns:
        Número de jobs ejecutados en este ciclo.
    """
    now = datetime.now(UTC)

    # Cargar TODOS los jobs CRON activos (sin filtro de tenant)
    jobs = (await session.scalars(
        select(Job).where(
            Job.kind == JobKind.CRON,
            Job.status == JobStatus.ACTIVE,
        )
    )).all()

    if not jobs:
        return 0

    executed = 0
    for job in jobs:
        result = await _process_job(session, job, now)
        if result:
            executed += 1

    if executed > 0:
        await session.commit()

    return executed
