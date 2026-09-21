"""Configuración de logging estructurado con structlog."""

import logging
import sys
from datetime import UTC, datetime

import structlog
from structlog.types import EventDict, Processor

from app.core.config import get_settings


def add_log_level(
    logger: structlog.BoundLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Añade el nivel de log al event_dict."""
    event_dict["level"] = method_name.upper()
    return event_dict


def add_timestamp(
    logger: structlog.BoundLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Añade timestamp ISO 8601."""
    event_dict["timestamp"] = datetime.now(UTC).isoformat()
    return event_dict


def setup_logging() -> None:
    """Configura structlog para logging JSON en producción, pretty en desarrollo."""
    settings = get_settings()

    # Procesadores compartidos
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        add_log_level,
        add_timestamp,
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.ENVIRONMENT == "development":
        # Desarrollo: pretty printing con colores
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # Producción: JSON estructurado
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Configurar logging estándar para librerías (uvicorn, sqlalchemy, etc.)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    )

    # Silenciar logs ruidosos de librerías en desarrollo
    if settings.ENVIRONMENT == "development":
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("asyncpg").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.BoundLogger:
    """Obtiene un logger estructurado para el módulo dado."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
