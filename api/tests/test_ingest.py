"""Tests HTTP para ingesta de métricas y servidores (API v1).

Patrón: ASGITransport + AsyncClient, registrar usuario -> login -> crear API key
via POST /auth/api-keys con Bearer -> usar X-Api-Key.
"""

from uuid import UUID

import pytest
from app.db.session import get_db_session
from app.main import app
from app.models.metric import Metric, MetricType
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
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


# ──────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_api_key_can_register_and_heartbeat_server() -> None:
    """Registrar server (201), heartbeat (200), verificar response."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _register_and_login(client, "owner1@example.com")
        api_key = await _create_api_key(client, token, "Agent 1")

        # Registrar server
        register_resp = await client.post(
            "/api/v1/servers/register",
            json={"hostname": "server1.example.com", "ip": "10.0.0.1", "os": "linux", "agent_version": "1.0.0"},
            headers={"X-Api-Key": api_key},
        )
        assert register_resp.status_code == 201
        server_data = register_resp.json()
        server_id = server_data["id"]
        assert server_data["hostname"] == "server1.example.com"
        assert server_data["status"] == "online"
        assert server_data["agent_version"] == "1.0.0"
        assert server_data["last_heartbeat_at"] is not None

        # Heartbeat
        hb_resp = await client.post(
            f"/api/v1/servers/{server_id}/heartbeat",
            headers={"X-Api-Key": api_key},
        )
        assert hb_resp.status_code == 200
        hb_data = hb_resp.json()
        assert hb_data["server_id"] == server_id
        assert "heartbeat_at" in hb_data


@pytest.mark.asyncio
async def test_register_upserts_existing_server() -> None:
    """Registrar dos veces mismo hostname -> 200 la segunda, mismo id."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _register_and_login(client, "owner2@example.com")
        api_key = await _create_api_key(client, token, "Agent 2")

        # Primera registración
        r1 = await client.post(
            "/api/v1/servers/register",
            json={"hostname": "upsert.example.com", "ip": "10.0.0.1", "os": "linux", "agent_version": "1.0.0"},
            headers={"X-Api-Key": api_key},
        )
        assert r1.status_code == 201
        server_id_1 = r1.json()["id"]

        # Segunda registración (mismo hostname, distinta IP)
        r2 = await client.post(
            "/api/v1/servers/register",
            json={"hostname": "upsert.example.com", "ip": "10.0.0.2", "os": "windows", "agent_version": "1.1.0"},
            headers={"X-Api-Key": api_key},
        )
        assert r2.status_code == 200  # upsert = 200
        server_data_2 = r2.json()
        assert server_data_2["id"] == server_id_1
        # Response solo incluye: id, hostname, status, agent_version, last_heartbeat_at
        assert server_data_2["agent_version"] == "1.1.0"
        assert server_data_2["status"] == "online"


@pytest.mark.asyncio
async def test_ingest_metrics_requires_server_of_tenant() -> None:
    """Cross-tenant: server de tenant A, ingest con API key de tenant B -> 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Tenant A: crear server
        token_a = await _register_and_login(client, "ownera@example.com")
        api_key_a = await _create_api_key(client, token_a, "Agent A")

        reg_a = await client.post(
            "/api/v1/servers/register",
            json={"hostname": "server-a.example.com"},
            headers={"X-Api-Key": api_key_a},
        )
        assert reg_a.status_code == 201
        server_id_a = reg_a.json()["id"]

        # Tenant B: intentar ingestar en server de A
        token_b = await _register_and_login(client, "ownerb@example.com")
        api_key_b = await _create_api_key(client, token_b, "Agent B")

        ingest_resp = await client.post(
            "/api/v1/ingest/metrics",
            json={
                "server_id": server_id_a,
                "metrics": [{"type": "cpu_usage", "value": 50.0}],
            },
            headers={"X-Api-Key": api_key_b},
        )
        assert ingest_resp.status_code == 404
        assert ingest_resp.json()["detail"] == "Server no encontrado"

        # Heartbeat cross-tenant también -> 404
        hb_resp = await client.post(
            f"/api/v1/servers/{server_id_a}/heartbeat",
            headers={"X-Api-Key": api_key_b},
        )
        assert hb_resp.status_code == 404


@pytest.mark.asyncio
async def test_ingest_metrics_persists_rows() -> None:
    """Ingestar 2 métricas válidas -> 202 y inserted == 2. Verificar persistencia en BD."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _register_and_login(client, "owner3@example.com")
        api_key = await _create_api_key(client, token, "Agent 3")

        # Registrar server
        reg_resp = await client.post(
            "/api/v1/servers/register",
            json={"hostname": "metrics-server.example.com"},
            headers={"X-Api-Key": api_key},
        )
        assert reg_resp.status_code == 201
        server_id = reg_resp.json()["id"]

        # Ingestar 2 métricas
        ingest_resp = await client.post(
            "/api/v1/ingest/metrics",
            json={
                "server_id": server_id,
                "metrics": [
                    {"type": "cpu_usage", "value": 42.5, "tags": {"core": "0"}},
                    {"type": "mem_usage", "value": 65.0, "tags": {}},
                ],
            },
            headers={"X-Api-Key": api_key},
        )
        assert ingest_resp.status_code == 202
        data = ingest_resp.json()
        assert data["received"] == 2
        assert data["inserted"] == 2
        assert data["server_id"] == server_id

        # Verificar persistencia directa en BD
        async with get_db_session() as session:
            # Contar métricas para este server
            server_uuid = UUID(server_id)
            count_result = await session.execute(
                select(func.count()).select_from(Metric).where(Metric.server_id == server_uuid)
            )
            count = count_result.scalar_one()
            assert count == 2

            # Verificar tenant_id correcto (via contexto del test no hay, pero el repo lo forzó)
            metrics_result = await session.execute(
                select(Metric).where(Metric.server_id == server_uuid)
            )
            metrics = metrics_result.scalars().all()
            assert len(metrics) == 2
            types = {m.type for m in metrics}
            assert MetricType.CPU_USAGE in types
            assert MetricType.MEM_USAGE in types


@pytest.mark.asyncio
async def test_ingest_payload_invalid() -> None:
    """Payload inválido: metrics vacío -> 422, type inválido -> 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _register_and_login(client, "owner4@example.com")
        api_key = await _create_api_key(client, token, "Agent 4")

        # Registrar server primero
        reg_resp = await client.post(
            "/api/v1/servers/register",
            json={"hostname": "invalid-payload.example.com"},
            headers={"X-Api-Key": api_key},
        )
        server_id = reg_resp.json()["id"]

        # metrics vacío -> 422
        resp_empty = await client.post(
            "/api/v1/ingest/metrics",
            json={"server_id": server_id, "metrics": []},
            headers={"X-Api-Key": api_key},
        )
        assert resp_empty.status_code == 422

        # type inválido -> 422
        resp_bad_type = await client.post(
            "/api/v1/ingest/metrics",
            json={"server_id": server_id, "metrics": [{"type": "invalid_type", "value": 1.0}]},
            headers={"X-Api-Key": api_key},
        )
        assert resp_bad_type.status_code == 422


@pytest.mark.asyncio
async def test_tenant_scoped_repo_works_over_http() -> None:
    """Verificación indirecta del fix T1: endpoints con API key funcionan sin RuntimeError.

    Si el ContextVar no se setea, TenantScopedRepository.__init__ lanza RuntimeError
    al llamar require_tenant_context(). Este test verifica que NO ocurre.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _register_and_login(client, "owner5@example.com")
        api_key = await _create_api_key(client, token, "Agent 5")

        # Registrar server
        reg_resp = await client.post(
            "/api/v1/servers/register",
            json={"hostname": "tenant-scope-test.example.com"},
            headers={"X-Api-Key": api_key},
        )
        assert reg_resp.status_code == 201
        server_id = reg_resp.json()["id"]

        # Heartbeat - usa ServerRepository (TenantScopedRepository)
        hb_resp = await client.post(
            f"/api/v1/servers/{server_id}/heartbeat",
            headers={"X-Api-Key": api_key},
        )
        assert hb_resp.status_code == 200

        # Ingest - usa ServerRepository y MetricRepository (ambos TenantScopedRepository)
        ingest_resp = await client.post(
            "/api/v1/ingest/metrics",
            json={"server_id": server_id, "metrics": [{"type": "cpu_usage", "value": 10.0}]},
            headers={"X-Api-Key": api_key},
        )
        assert ingest_resp.status_code == 202

        # Si llegamos aquí sin 500 (RuntimeError), el fix T1 funciona
        # Verificación adicional: cross-tenant 404 confirma que el repo filtra por tenant
        token_b = await _register_and_login(client, "owner5b@example.com")
        api_key_b = await _create_api_key(client, token_b, "Agent 5B")

        hb_cross = await client.post(
            f"/api/v1/servers/{server_id}/heartbeat",
            headers={"X-Api-Key": api_key_b},
        )
        assert hb_cross.status_code == 404
