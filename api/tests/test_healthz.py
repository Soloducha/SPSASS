"""Tests para health checks."""

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_healthz_structure() -> None:
    """Health check debería responder con estructura correcta (200 o 503 según deps)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    # Acepta 200 (todo ok) o 503 (deps caídas) - ambos son respuestas válidas
    assert response.status_code in (200, 503)
    data = response.json()
    assert "api" in data
    assert "database" in data
    assert "redis" in data
    assert data["api"] == "ok"


@pytest.mark.asyncio
async def test_readyz_structure() -> None:
    """Readiness check debería responder con estructura correcta."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")

    assert response.status_code in (200, 503)
    data = response.json()
    assert "api" in data
    assert "database" in data
    assert "redis" in data
