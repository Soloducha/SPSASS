"""Entry point para workers arq.

Registra los cron jobs de rollups (1m/5m/1h/1d) y de alertas (1m). Cada
job delega con una sesión SIN contexto de tenant: los rollups agregan
métricas de TODOS los tenants y la evaluación de alertas evalúa las
reglas activas de TODOS los tenants en un solo pase.
"""

import asyncio
from typing import Any

from arq.connections import RedisSettings
from arq.cron import CronJob, cron
from arq.typing import StartupShutdown, WorkerSettingsBase
from arq.worker import Function, Worker, create_worker, func

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.session import get_db_session_without_tenant
from app.models.metric_rollup import RollupPeriod
from app.workers.alerts import evaluate_alerts
from app.workers.rollups import compute_rollups

setup_logging()
logger = get_logger(__name__)
settings = get_settings()


async def on_startup(ctx: dict[str, Any]) -> None:
    """Inicialización al arrancar worker."""
    logger.info("worker_starting")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    """Limpieza al apagar worker."""
    logger.info("worker_shutting_down")


# ──────────────────────────────────────────────
# Jobs de rollups (un wrapper por periodo: arq 0.28
# no permite pasar kwargs a coroutines de cron).
# ──────────────────────────────────────────────
async def rollup_metrics_row(ctx: dict[str, Any], period: RollupPeriod) -> int:
    """Rollups de un período sobre TODOS los tenants (sin contexto tenant)."""
    async with get_db_session_without_tenant() as session:
        return await compute_rollups(session, period)


async def rollup_min_1(ctx: dict[str, Any]) -> int:
    """Rollups 1m (corre cada minuto, window 15 min)."""
    return await rollup_metrics_row(ctx, RollupPeriod.MIN_1)


async def rollup_min_5(ctx: dict[str, Any]) -> int:
    """Rollups 5m (corre cada 5 min, window 2 h)."""
    return await rollup_metrics_row(ctx, RollupPeriod.MIN_5)


async def rollup_hour_1(ctx: dict[str, Any]) -> int:
    """Rollups 1h (corre cada hora, window 48 h)."""
    return await rollup_metrics_row(ctx, RollupPeriod.HOUR_1)


async def rollup_day_1(ctx: dict[str, Any]) -> int:
    """Rollups 1d (corre a medianoche, window 14 días)."""
    return await rollup_metrics_row(ctx, RollupPeriod.DAY_1)


# ──────────────────────────────────────────────
# Job de alertas (evaluación cada minuto).
# ──────────────────────────────────────────────
async def evaluate_alerts_row(ctx: dict[str, Any]) -> int:
    """Evalúa reglas de alerta activas sobre TODOS los tenants (sin contexto tenant)."""
    async with get_db_session_without_tenant() as session:
        return await evaluate_alerts(session)


class WorkerSettings(WorkerSettingsBase):
    """Configuración de workers arq (convención: atributos → kwargs de Worker)."""

    redis_settings = RedisSettings.from_dsn(str(settings.REDIS_URL))
    functions: list[Function] = [
        func(rollup_min_1),
        func(rollup_min_5),
        func(rollup_hour_1),
        func(rollup_day_1),
        func(evaluate_alerts_row),
    ]
    cron_jobs: list[CronJob] = [
        cron(rollup_min_1, name="rollup-1m", run_at_startup=False, unique=True),
        cron(rollup_min_5, name="rollup-5m", minute=set(range(0, 60, 5)), run_at_startup=False, unique=True),
        cron(rollup_hour_1, name="rollup-1h", minute=0, second=0, run_at_startup=False, unique=True),
        cron(rollup_day_1, name="rollup-1d", hour=0, minute=0, second=0, run_at_startup=False, unique=True),
        cron(evaluate_alerts_row, name="alert-eval-1m", run_at_startup=False, unique=True),
    ]
    on_startup: StartupShutdown | None = on_startup
    on_shutdown: StartupShutdown | None = on_shutdown


async def main() -> None:
    """Punto de entrada: arranca el worker real (usado por Dockerfile.worker)."""
    logger.info("worker_main_starting")
    worker: Worker = create_worker(WorkerSettings)
    await worker.async_run()


if __name__ == "__main__":
    asyncio.run(main())
