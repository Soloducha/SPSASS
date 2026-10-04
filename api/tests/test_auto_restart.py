"""Tests de integración para auto-restart (T5).

Cubre flujo completo: encolar → agente poll → ejecutar → reportar → verificar status.
Y worker: alerta SERVICE/PROCESS con auto_restart=true → comando encolado.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.db.session import get_db_session
from app.main import app
from app.models.agent_command import AgentCommand, AgentCommandStatus
from app.models.alert import Alert, AlertOperator, AlertRule, AlertSeverity, AlertStatus, EntityType
from app.models.process import Process
from app.models.server import Server, ServerStatus
from app.models.service import Service, ServiceState
from app.models.tenant import Tenant
from app.workers.alerts import evaluate_alerts
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# ──────────────────────────────────────────────
# Helpers de autenticación (patrón test_alerts.py)
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


async def _create_server_via_api(client: AsyncClient, api_key: str, hostname: str) -> str:
    """Registra un server y retorna su ID."""
    reg_resp = await client.post(
        "/api/v1/servers/register",
        json={"hostname": hostname},
        headers={"X-Api-Key": api_key},
    )
    assert reg_resp.status_code == 201
    return reg_resp.json()["id"]


async def _get_tenant_id_from_me(client: AsyncClient, token: str) -> str:
    """Obtiene el tenant_id del usuario autenticado vía /auth/me."""
    me_resp = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    return me_resp.json()["tenant_id"]


async def _enqueue_restart_via_api(
    client: AsyncClient, token: str, server_id: str, entity_type: str, entity_name: str
) -> dict:
    """Encola un comando de restart vía API (JWT user)."""
    resp = await client.post(
        f"/api/v1/servers/{server_id}/restart",
        json={"entity_type": entity_type, "entity_name": entity_name},
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()


async def _seed_service_via_api(
    client: AsyncClient, token: str, server_id: str, name: str, auto_restart: bool = True
) -> str:
    """Crea un servicio vía API y retorna su ID (requiere JWT)."""
    resp = await client.post(
        "/api/v1/services",
        json={"server_id": server_id, "name": name, "desired_state": "running", "auto_restart": auto_restart},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _seed_process_via_api(
    client: AsyncClient, token: str, server_id: str, name: str, auto_restart: bool = True
) -> str:
    """Crea un proceso vía API y retorna su ID (requiere JWT)."""
    resp = await client.post(
        "/api/v1/processes",
        json={"server_id": server_id, "name": name, "pattern": name, "expected_count": 1, "auto_restart": auto_restart},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ──────────────────────────────────────────────
# Helpers de BD directa
# ──────────────────────────────────────────────
async def _seed_tenant_server(session: AsyncSession) -> tuple[Tenant, Server]:
    """Crea tenant + server de prueba y devuelve ambos."""
    tenant = Tenant(name="ar-tenant", slug=f"ar-{uuid4().hex[:8]}")
    session.add(tenant)
    await session.flush()

    server = Server(
        tenant_id=tenant.id,
        hostname=f"server-{uuid4().hex[:8]}",
        ip="10.0.0.1",
        os="linux",
        status=ServerStatus.ONLINE,
    )
    session.add(server)
    await session.flush()
    return tenant, server


async def _seed_service(
    session: AsyncSession, tenant: Tenant, server: Server, name: str, auto_restart: bool = True
) -> Service:
    """Crea un servicio de prueba."""
    service = Service(
        tenant_id=tenant.id,
        server_id=server.id,
        name=name,
        desired_state=ServiceState.RUNNING,
        auto_restart=auto_restart,
        last_status=ServiceState.RUNNING,
    )
    session.add(service)
    await session.flush()
    return service


async def _seed_process(
    session: AsyncSession, tenant: Tenant, server: Server, name: str, auto_restart: bool = True
) -> Process:
    """Crea un proceso de prueba."""
    process = Process(
        tenant_id=tenant.id,
        server_id=server.id,
        name=name,
        pattern=name,
        expected_count=1,
        auto_restart=auto_restart,
        last_count=1,
    )
    session.add(process)
    await session.flush()
    return process


# ──────────────────────────────────────────────
# Tests de API: encolar → listar → reportar resultado
# ──────────────────────────────────────────────
class TestAutoRestartAPI:
    """Tests de integración API para agent_commands."""

    @pytest.mark.asyncio
    async def test_enqueue_restart_endpoint(self, async_client: AsyncClient) -> None:
        """POST /restart encola un comando correctamente."""
        client = async_client
        token = await _register_and_login(client, "ar_enqueue_owner@example.com")
        api_key = await _create_api_key(client, token, "Agent Enqueue")
        server_id = await _create_server_via_api(client, api_key, "ar-enqueue-server")
        await _seed_service_via_api(client, token, server_id, "nginx", auto_restart=True)

        enqueue_resp = await client.post(
            f"/api/v1/servers/{server_id}/restart",
            json={"entity_type": "service", "entity_name": "nginx"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert enqueue_resp.status_code == 201
        command = enqueue_resp.json()
        command_id = command["id"]
        assert command["entity_type"] == "service"
        assert command["entity_name"] == "nginx"
        assert command["status"] == "pending"
        assert command["server_id"] == server_id

    @pytest.mark.asyncio
    async def test_list_pending_commands_endpoint(self, async_client: AsyncClient, db_session: AsyncSession) -> None:
        """GET /commands lista comandos pendientes para un servidor."""
        client = async_client
        token = await _register_and_login(client, "ar_list_owner@example.com")
        api_key = await _create_api_key(client, token, "Agent List")
        server_id = await _create_server_via_api(client, api_key, "ar-list-server")
        await _seed_service_via_api(client, token, server_id, "nginx", auto_restart=True)
        tenant_id = await _get_tenant_id_from_me(client, token)

        # Pre-crear un comando PENDING directamente en BD
        from app.models.agent_command import AgentCommand, AgentCommandStatus
        from datetime import UTC, datetime
        command = AgentCommand(
            tenant_id=UUID(tenant_id),
            server_id=UUID(server_id),
            entity_type="service",
            entity_name="nginx",
            status=AgentCommandStatus.PENDING,
            scheduled_at=datetime.now(UTC),
        )
        db_session.add(command)
        await db_session.flush()
        await db_session.commit()
        command_id = command.id

        # Listar comandos pendientes
        list_resp = await client.get(
            f"/api/v1/servers/{server_id}/commands",
            headers={"X-Api-Key": api_key},
        )
        assert list_resp.status_code == 200
        commands = list_resp.json()
        assert len(commands) == 1
        assert commands[0]["id"] == str(command_id)
        # AgentCommandPendingResponse no incluye status (es implícito "pending")

        # Verificar que el comando se marcó como RUNNING
        await db_session.refresh(command)
        assert command.status == AgentCommandStatus.RUNNING
        assert command.started_at is not None

    @pytest.mark.asyncio
    async def test_report_command_result_success_endpoint(self, async_client: AsyncClient, db_session: AsyncSession) -> None:
        """PATCH /result con status=success actualiza el comando correctamente."""
        client = async_client
        token = await _register_and_login(client, "ar_report_owner@example.com")
        api_key = await _create_api_key(client, token, "Agent Report")
        server_id = await _create_server_via_api(client, api_key, "ar-report-server")
        await _seed_service_via_api(client, token, server_id, "nginx", auto_restart=True)
        tenant_id = await _get_tenant_id_from_me(client, token)

        # Pre-crear un comando RUNNING (simula que el agente lo tomó)
        from app.models.agent_command import AgentCommand, AgentCommandStatus
        from datetime import UTC, datetime
        command = AgentCommand(
            tenant_id=UUID(tenant_id),
            server_id=UUID(server_id),
            entity_type="service",
            entity_name="nginx",
            status=AgentCommandStatus.RUNNING,
            scheduled_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
        )
        db_session.add(command)
        await db_session.flush()
        await db_session.commit()
        command_id = command.id

        # Reportar resultado success
        report_resp = await client.patch(
            f"/api/v1/servers/agent-commands/{command_id}/result",
            json={"status": "success", "exit_code": 0, "output_tail": "nginx restarted successfully"},
            headers={"X-Api-Key": api_key},
        )
        assert report_resp.status_code == 200

        # Verificar estado final en BD
        await db_session.refresh(command)
        assert command.status == AgentCommandStatus.SUCCESS
        assert command.exit_code == 0
        assert command.output_tail == "nginx restarted successfully"
        assert command.finished_at is not None
        assert command.started_at is not None

    @pytest.mark.asyncio
    async def test_report_command_result_failed_endpoint(self, async_client: AsyncClient, db_session: AsyncSession) -> None:
        """PATCH /result con status=failed actualiza el comando correctamente."""
        client = async_client
        token = await _register_and_login(client, "ar_report_fail_owner@example.com")
        api_key = await _create_api_key(client, token, "Agent ReportFail")
        server_id = await _create_server_via_api(client, api_key, "ar-report-fail-server")
        await _seed_process_via_api(client, token, server_id, "bad-process", auto_restart=True)
        tenant_id = await _get_tenant_id_from_me(client, token)

        # Pre-crear un comando RUNNING
        from app.models.agent_command import AgentCommand, AgentCommandStatus
        from datetime import UTC, datetime
        command = AgentCommand(
            tenant_id=UUID(tenant_id),
            server_id=UUID(server_id),
            entity_type="process",
            entity_name="bad-process",
            status=AgentCommandStatus.RUNNING,
            scheduled_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
        )
        db_session.add(command)
        await db_session.flush()
        await db_session.commit()
        command_id = command.id

        # Reportar fallo
        report_resp = await client.patch(
            f"/api/v1/servers/agent-commands/{command_id}/result",
            json={"status": "failed", "exit_code": 1, "output_tail": "process not found"},
            headers={"X-Api-Key": api_key},
        )
        assert report_resp.status_code == 200

        # Verificar estado final en BD
        await db_session.refresh(command)
        assert command.status == AgentCommandStatus.FAILED
        assert command.exit_code == 1
        assert "process not found" in command.output_tail
        assert command.finished_at is not None
        assert command.started_at is not None

    @pytest.mark.asyncio
    async def test_enqueue_duplicate_returns_409(self, async_client: AsyncClient) -> None:
        """Encolar comando duplicado para misma entidad → 409 CONFLICT."""
        client = async_client
        token = await _register_and_login(client, "ar_dup_owner@example.com")
        api_key = await _create_api_key(client, token, "Agent DUP")
        server_id = await _create_server_via_api(client, api_key, "ar-dup-server")
        await _seed_service_via_api(client, token, server_id, "nginx", auto_restart=True)

        # Primer comando
        resp1 = await client.post(
            f"/api/v1/servers/{server_id}/restart",
            json={"entity_type": "service", "entity_name": "nginx"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp1.status_code == 201

        # Segundo comando para misma entidad → 409
        resp2 = await client.post(
            f"/api/v1/servers/{server_id}/restart",
            json={"entity_type": "service", "entity_name": "nginx"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 409
        assert "Ya hay un comando pendiente" in resp2.json()["detail"]

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation(self, async_client: AsyncClient) -> None:
        """Comandos de tenant A no visibles para tenant B."""
        client = async_client
        # Tenant A
        token_a = await _register_and_login(client, "ar_tenant_a@example.com")
        api_key_a = await _create_api_key(client, token_a, "Agent A")
        server_id_a = await _create_server_via_api(client, api_key_a, "ar-server-a")
        await _seed_service_via_api(client, token_a, server_id_a, "nginx", auto_restart=True)

        await client.post(
            f"/api/v1/servers/{server_id_a}/restart",
            json={"entity_type": "service", "entity_name": "nginx"},
            headers={"Authorization": f"Bearer {token_a}"},
        )

        # Tenant B
        token_b = await _register_and_login(client, "ar_tenant_b@example.com")
        api_key_b = await _create_api_key(client, token_b, "Agent B")
        server_id_b = await _create_server_via_api(client, api_key_b, "ar-server-b")

        # B lista sus comandos → vacío
        list_b = await client.get(
            f"/api/v1/servers/{server_id_b}/commands",
            headers={"X-Api-Key": api_key_b},
        )
        assert list_b.status_code == 200
        assert len(list_b.json()) == 0

        # B intenta ver comandos de A (diferente server_id, distinto tenant) → 404
        list_b2 = await client.get(
            f"/api/v1/servers/{server_id_a}/commands",
            headers={"X-Api-Key": api_key_b},
        )
        assert list_b2.status_code == 404
            # En este caso server_id_b no tiene comandos, así que lista vacía


# ──────────────────────────────────────────────
# Tests de Worker: alerta SERVICE/PROCESS con auto_restart → comando encolado
# ──────────────────────────────────────────────
class TestWorkerAutoRestart:
    """Tests de que el worker encola auto-restart al crear alerta SERVICE/PROCESS."""

    async def test_service_auto_restart_enqueues_command(self, db_session: AsyncSession) -> None:
        """Alerta SERVICE con auto_restart=true → AgentCommand PENDING creado."""
        tenant, server = await _seed_tenant_server(db_session)

        # Service con auto_restart=True y status != desired (violando)
        service = await _seed_service(db_session, tenant, server, "nginx", auto_restart=True)
        service.last_status = ServiceState.STOPPED  # violación
        await db_session.flush()

        # Regla SERVICE para este servicio
        rule = AlertRule(
            tenant_id=tenant.id,
            entity_type=EntityType.SERVICE,
            entity_id=service.id,
            metric="service_status",  # no usado directamente, worker usa last_status vs desired_state
            operator=AlertOperator.NEQ,  # desired != actual
            threshold=0,  # no usado
            duration_s=60,
            severity=AlertSeverity.WARNING,
            channels={"email": {}},
            is_active=True,
        )
        db_session.add(rule)
        await db_session.flush()

        # Ejecutar worker
        created = await evaluate_alerts(db_session)
        assert created == 1

        # Verificar alerta creada
        alert = await db_session.scalar(
            select(Alert).where(Alert.rule_id == rule.id)
        )
        assert alert is not None
        assert alert.status == AlertStatus.OPEN

        # Verificar AgentCommand creado
        cmd = await db_session.scalar(
            select(AgentCommand).where(
                AgentCommand.server_id == server.id,
                AgentCommand.entity_type == "service",
                AgentCommand.entity_name == "nginx",
            )
        )
        assert cmd is not None
        assert cmd.status == AgentCommandStatus.PENDING
        assert cmd.tenant_id == tenant.id

    async def test_process_auto_restart_enqueues_command(self, db_session: AsyncSession) -> None:
        """Alerta PROCESS con auto_restart=true → AgentCommand PENDING creado."""
        tenant, server = await _seed_tenant_server(db_session)

        # Process con auto_restart=True y count < expected (violando)
        process = await _seed_process(db_session, tenant, server, "nginx-worker", auto_restart=True)
        process.last_count = 0  # violación (expected=1)
        process.last_checked_at = datetime.now(UTC)
        await db_session.flush()

        # Regla PROCESS para este proceso
        rule = AlertRule(
            tenant_id=tenant.id,
            entity_type=EntityType.PROCESS,
            entity_id=process.id,
            metric="process_count",
            operator=AlertOperator.LT,
            threshold=1,
            duration_s=60,
            severity=AlertSeverity.WARNING,
            channels={"email": {}},
            is_active=True,
        )
        db_session.add(rule)
        await db_session.flush()

        # Ejecutar worker
        created = await evaluate_alerts(db_session)
        assert created == 1

        # Verificar AgentCommand creado
        cmd = await db_session.scalar(
            select(AgentCommand).where(
                AgentCommand.server_id == server.id,
                AgentCommand.entity_type == "process",
                AgentCommand.entity_name == "nginx-worker",
            )
        )
        assert cmd is not None
        assert cmd.status == AgentCommandStatus.PENDING
        assert cmd.tenant_id == tenant.id

    async def test_no_auto_restart_when_disabled(self, db_session: AsyncSession) -> None:
        """Service sin auto_restart → NO se encola comando."""
        tenant, server = await _seed_tenant_server(db_session)

        service = await _seed_service(db_session, tenant, server, "nginx", auto_restart=False)
        service.last_status = ServiceState.STOPPED
        await db_session.flush()

        rule = AlertRule(
            tenant_id=tenant.id,
            entity_type=EntityType.SERVICE,
            entity_id=service.id,
            metric="service_status",
            operator=AlertOperator.NEQ,
            threshold=0,
            duration_s=60,
            severity=AlertSeverity.WARNING,
            channels={"email": {}},
            is_active=True,
        )
        db_session.add(rule)
        await db_session.flush()

        created = await evaluate_alerts(db_session)
        assert created == 1

        # NO debe haber AgentCommand
        cmd = await db_session.scalar(
            select(AgentCommand).where(
                AgentCommand.server_id == server.id,
                AgentCommand.entity_type == "service",
                AgentCommand.entity_name == "nginx",
            )
        )
        assert cmd is None

async def test_idempotency_no_duplicate_commands(db_session: AsyncSession) -> None:
        """Si ya hay comando PENDING/RUNNING, no se encola otro."""
        tenant, server = await _seed_tenant_server(db_session)

        service = await _seed_service(db_session, tenant, server, "nginx", auto_restart=True)
        service.last_status = ServiceState.STOPPED
        await db_session.flush()

        # Pre-crear comando PENDING
        from datetime import UTC, datetime
        from app.models.agent_command import AgentCommandEntityType
        existing_cmd = AgentCommand(
            tenant_id=tenant.id,
            server_id=server.id,
            entity_type=AgentCommandEntityType.SERVICE,
            entity_name="nginx",
            status=AgentCommandStatus.PENDING,
            scheduled_at=datetime.now(UTC),
        )
        db_session.add(existing_cmd)
        await db_session.flush()
        await db_session.commit()

        rule = AlertRule(
            tenant_id=tenant.id,
            entity_type=EntityType.SERVICE,
            entity_id=service.id,
            metric="service_status",
            operator=AlertOperator.NEQ,
            threshold=0,
            duration_s=60,
            severity=AlertSeverity.WARNING,
            channels={"email": {}},
            is_active=True,
        )
        db_session.add(rule)
        await db_session.flush()

        # Ejecutar worker
        created = await evaluate_alerts(db_session)
        assert created == 1

        # Debe seguir habiendo SOLO 1 comando
        cmds = (await db_session.scalars(
            select(AgentCommand).where(
                AgentCommand.server_id == server.id,
                AgentCommand.entity_type == AgentCommandEntityType.SERVICE,
                AgentCommand.entity_name == "nginx",
            )
        )).all()
        assert len(cmds) == 1
        assert cmds[0].id == existing_cmd.id