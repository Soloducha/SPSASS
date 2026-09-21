"""Configuración de base de datos: SQLAlchemy 2.0 async + session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.tenant.context import get_tenant_context
from app.models.base import Base

logger = get_logger(__name__)
settings = get_settings()


# Engine singleton
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Obtiene o crea el engine async de SQLAlchemy."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            str(settings.DATABASE_URL),
            echo=settings.ENVIRONMENT == "development",
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
        logger.info("database_engine_created", url=str(settings.DATABASE_URL).split("@")[-1])
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Obtiene o crea el factory de sesiones."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager para obtener una sesión de BD.
    Uso:
        async with get_db_session() as session:
            ...
    Inyecta automáticamente app.tenant_id en PostgreSQL si hay contexto de tenant.
    """
    session = get_session_factory()()
    try:
        # Inyectar tenant_id en sesión PostgreSQL para RLS
        tenant_ctx = get_tenant_context()
        if tenant_ctx:
            await session.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(tenant_ctx.tenant_id)})
            logger.debug("db_session_tenant_injected", tenant_id=str(tenant_ctx.tenant_id))

        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@asynccontextmanager
async def get_db_session_without_tenant() -> AsyncGenerator[AsyncSession, None]:
    """
    Sesión de BD SIN inyección de tenant (para operaciones admin, migraciones, etc.).
    Úsala con precaución: bypassa RLS completamente.
    """
    session = get_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db() -> None:
    """Inicializa la BD: crea tablas si no existen (para dev/test)."""
    # En producción usamos Alembic migrations
    if settings.ENVIRONMENT != "production":
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database_tables_created")


async def close_db() -> None:
    """Cierra el engine de BD."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("database_engine_closed")
