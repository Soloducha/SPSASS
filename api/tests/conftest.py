"""Configuración compartida de pytest."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("TESTING", "1")  # Activa hash sha256_crypt en tests

import pytest_asyncio
import sqlalchemy as sa
from app.db.session import close_db, get_db_session, get_engine, init_db
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def async_client() -> AsyncClient:
    """Cliente HTTP asíncrono para testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Sesión de BD para tests que necesitan acceso directo."""
    async with get_db_session() as session:
        yield session


@pytest_asyncio.fixture(autouse=True, scope="function")
async def initialize_database() -> None:
    """Recrea el engine en el event loop de cada test (pytest-asyncio crea un
    loop por test; asyncpg no permite reutilizar conexiones entre loops).
    Con SQLite StaticPool no se notaba; con Postgres real es obligatorio.
    Además, en Postgres real limpia las tablas de negocio antes de cada test
    para aislamiento (SQLite en memoria ya lo hace por defecto)."""
    global _engine, _session_factory
    # Resetear singletons para que usen la nueva DATABASE_URL y el loop actual
    _engine = None
    _session_factory = None
    await init_db()

    # Limpieza condicional para Postgres real (no SQLite)
    engine = get_engine()
    if engine.dialect.name != "sqlite":
        # Orden de dependencias: hijos primero, padres después
        tables = [
            "alert_deliveries",
            "alerts",
            "alert_rules",
            "job_runs",
            "jobs",
            "reports",
            "metrics",
            "metric_rollups",
            "services",
            "processes",
            "servers",
            "api_keys",
            "tenant_members",
            "users",
            "tenants",
        ]
        async with engine.begin() as conn:
            for table in tables:
                await conn.execute(sa.text(f'TRUNCATE "{table}" RESTART IDENTITY CASCADE'))

    yield
    await close_db()
