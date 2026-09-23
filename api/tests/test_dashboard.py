"""Tests HTTP del dashboard overview (API v1).

Patrón: registrar usuario -> login -> crear API key -> registrar server ->
ingestar métricas -> GET /api/v1/dashboard/overview con JWT.
"""

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


async def _register_and_login(client: AsyncClient, email: str) -> str:
    """Registra usuario, hace login y retorna access_token."""
    await client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": email.split("@", maxsplit=1)[0]},
    )
    login_resp = await client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    return login_resp.json()["access_token"]


async def _create_api_key(client: AsyncClient, token: str, name: str) -> str:
    """Crea API key y retorna raw_key."""
    create_resp = await client.post(
        "/auth/api-keys",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201
    return create_resp.json()["raw_key"]


async def _register_server(client: AsyncClient, api_key: str, hostname: str) -> str:
    """Registra un server con la API key y retorna server_id."""
    resp = await client.post(
        "/api/v1/servers/register",
        json={"hostname": hostname, "ip": "10.0.0.1", "os": "linux", "agent_version": "1.0.0"},
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _ingest_metrics(
    client: AsyncClient, api_key: str, server_id: str, metrics: list[dict]
) -> None:
    resp = await client.post(
        "/api/v1/ingest/metrics",
        json={"server_id": server_id, "metrics": metrics},
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 202, resp.text


@pytest.mark.asyncio
async def test_dashboard_overview_requires_jwt() -> None:
    """GET /overview sin token -> 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/dashboard/overview")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_overview_empty_tenant() -> None:
    """Tenant sin servers -> totals en cero y lista vacía."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _register_and_login(client, "owner-dash0@example.com")

        resp = await client.get(
            "/api/v1/dashboard/overview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"] == {
            "total": 0,
            "online": 0,
            "offline": 0,
            "degraded": 0,
            "unknown": 0,
        }
        assert data["servers"] == []


@pytest.mark.asyncio
async def test_dashboard_overview_with_server_and_latest_metrics() -> None:
    """Server online + métricas ingeridas -> totals y latest_metrics correctos."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _register_and_login(client, "owner-dash1@example.com")
        api_key = await _create_api_key(client, token, "Agent Dash")
        server_id = await _register_server(client, api_key, "dash.example.com")

        # Dos rondas: la última observación gana
        await _ingest_metrics(
            client,
            api_key,
            server_id,
            [{"type": "cpu_usage", "value": 10.0}, {"type": "mem_usage", "value": 20.0}],
        )
        await _ingest_metrics(
            client,
            api_key,
            server_id,
            [{"type": "cpu_usage", "value": 55.5}, {"type": "disk_usage", "value": 70.0}],
        )

        resp = await client.get(
            "/api/v1/dashboard/overview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"]["total"] == 1
        assert data["totals"]["online"] == 1

        server = data["servers"][0]
        assert server["id"] == server_id
        assert server["hostname"] == "dash.example.com"
        assert server["ip"] == "10.0.0.1"
        assert server["os"] == "linux"
        assert server["status"] == "online"
        assert server["last_heartbeat_at"] is not None
        # Últimas observaciones: cpu 55.5 (segunda ronda) y mem 20.0, disk 70.0
        assert server["latest_metrics"]["cpu_usage"] == 55.5
        assert server["latest_metrics"]["mem_usage"] == 20.0
        assert server["latest_metrics"]["disk_usage"] == 70.0


@pytest.mark.asyncio
async def test_dashboard_overview_cross_tenant_isolation() -> None:
    """Servers/metrics del tenant A no aparecen en el dashboard del tenant B."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Tenant A: server + métricas
        token_a = await _register_and_login(client, "owner-dasha@example.com")
        api_key_a = await _create_api_key(client, token_a, "Agent Dash A")
        server_a = await _register_server(client, api_key_a, "a.example.com")
        await _ingest_metrics(
            client,
            api_key_a,
            server_a,
            [{"type": "cpu_usage", "value": 99.0}],
        )

        # Tenant B: verifica vacío
        token_b = await _register_and_login(client, "owner-dashb@example.com")
        resp_b = await client.get(
            "/api/v1/dashboard/overview",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp_b.status_code == 200
        data_b = resp_b.json()
        assert data_b["totals"]["total"] == 0
        assert data_b["servers"] == []

        # Tenant A: ve su server
        resp_a = await client.get(
            "/api/v1/dashboard/overview",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        data_a = resp_a.json()
        assert data_a["totals"]["total"] == 1
        assert data_a["servers"][0]["id"] == server_a
        assert data_a["servers"][0]["latest_metrics"]["cpu_usage"] == 99.0
