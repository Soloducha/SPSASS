"""Configuración compartida de pytest - SQLite para tests unitarios (compatible Windows)."""

import os
import tempfile

# SQLite archivo temporal para tests unitarios (compatible Windows)
_db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_db_file.name}")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("TESTING", "1")

import pytest_asyncio
import sqlalchemy as sa
from app.db.session import close_db, get_db_session, get_engine, init_db
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database_engine():
    """Inicializa el engine una vez por sesión de test."""
    engine = get_engine()
    await init_db()
    yield
    await close_db()


@pytest_asyncio.fixture(autouse=True, scope="function")
async def clean_database():
    """Limpia tablas antes de cada test (mantiene el engine vivo)."""
    engine = get_engine()
    # SQLite no soporta TRUNCATE ... RESTART IDENTITY CASCADE
    # Usar DELETE FROM para cada tabla
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
            await conn.execute(sa.text(f'DELETE FROM "{table}"'))
            # Resetear autoincrement para SQLite (solo si existe sqlite_sequence)
            # Ignorar error si sqlite_sequence no existe aún
            try:
                await conn.execute(sa.text(f'DELETE FROM sqlite_sequence WHERE name="{table}"'))
            except Exception:
                pass  # sqlite_sequence no existe aún
    yield


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