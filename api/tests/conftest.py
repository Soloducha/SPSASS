"""Configuración compartida de pytest."""

import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"  # healthz lo chequea, tolera fallo
os.environ["TESTING"] = "1"  # Activa hash sha256_crypt en tests

import pytest_asyncio
from app.db.session import close_db, get_db_session, init_db
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


@pytest_asyncio.fixture(autouse=True, scope="session")
async def initialize_database() -> None:
    """Inicializa BD al inicio de la sesión de tests."""
    global _engine, _session_factory
    # Resetear singletons para que usen la nueva DATABASE_URL
    _engine = None
    _session_factory = None
    await init_db()
    yield
    await close_db()
