"""Entry point para workers arq."""

import asyncio
from typing import Any

from arq.connections import RedisSettings
from arq.cron import CronJob
from arq.worker import Function

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)
settings = get_settings()


async def on_startup(ctx: dict[str, Any]) -> None:
    """Inicialización al arrancar worker."""
    logger.info("worker_starting")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    """Limpieza al apagar worker."""
    logger.info("worker_shutting_down")


class WorkerSettings:
    """Configuración de workers arq."""

    redis_settings = RedisSettings.from_dsn(str(settings.REDIS_URL))
    # Jobs se registrarán en T4+
    functions: list[Function] = []
    cron_jobs: list[CronJob] = []
    on_startup = on_startup
    on_shutdown = on_shutdown


async def main() -> None:
    """Punto de entrada principal para ejecutar worker."""
    logger.info("worker_main_starting")
    # Para desarrollo, podemos usar arq.cli directamente
    # Este archivo existe para que Dockerfile.worker tenga un entrypoint
    pass


if __name__ == "__main__":
    asyncio.run(main())
