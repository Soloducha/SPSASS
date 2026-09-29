"""Tests para CRUD de Procesos, Servicios y Jobs (T1).

Cubre: CRUD happy path, aislamiento por tenant, JobRun list under job.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.models.job import Job, JobKind, JobRun
from app.models.server import Server, ServerStatus
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


# ──────────────────────────────────────────────
# Helpers de autenticación
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


async def _create_server_via_db(session: AsyncSession, tenant_id: UUID) -> Server:
    """Crea un server directamente en BD para tests."""
    server = Server(
        tenant_id=tenant_id,
        hostname=f"server-{uuid4().hex[:8]}",
        ip="10.0.0.1",
        os="linux",
        status=ServerStatus.ONLINE,
    )
    session.add(server)
    await session.flush()
    return server


async def _get_tenant_id_from_token(client: AsyncClient, token: str) -> str:
    """Obtiene el tenant_id del usuario autenticado vía /auth/me."""
    me_resp = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    return me_resp.json()["tenant_id"]


# ──────────────────────────────────────────────
# Tests PROCESSES
# ──────────────────────────────────────────────
class TestProcessesCRUD:
    """Tests CRUD de procesos."""

    @pytest.mark.asyncio
    async def test_create_list_get_patch_delete_process(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """CRUD completo de proceso."""
        client = async_client
        token = await _register_and_login(client, "process_owner@example.com")
        tenant_id = await _get_tenant_id_from_token(client, token)

        # Crear server primero (necesario por FK)
        server = await _create_server_via_db(db_session, UUID(tenant_id))
        server_id = str(server.id)
        await db_session.commit()

        # Crear proceso
        create_resp = await client.post(
            "/api/v1/processes",
            json={
                "server_id": server_id,
                "name": "nginx",
                "pattern": "nginx.*master",
                "expected_count": 1,
                "auto_restart": True,
                "config": {"key": "value"},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_resp.status_code == 201
        process_data = create_resp.json()
        process_id = process_data["id"]
        assert process_data["name"] == "nginx"
        assert process_data["pattern"] == "nginx.*master"
        assert process_data["expected_count"] == 1
        assert process_data["auto_restart"] is True
        assert process_data["config"] == {"key": "value"}
        assert process_data["tenant_id"] == tenant_id
        assert process_data["server_id"] == server_id

        # Listar procesos
        list_resp = await client.get(
            "/api/v1/processes",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        processes = list_resp.json()
        assert len(processes) == 1
        assert processes[0]["id"] == process_id

        # Filtrar por server_id
        list_filtered = await client.get(
            f"/api/v1/processes?server_id={server_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_filtered.status_code == 200
        assert len(list_filtered.json()) == 1

        # Obtener un proceso
        get_resp = await client.get(
            f"/api/v1/processes/{process_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == process_id

        # Actualizar proceso (patch parcial)
        patch_resp = await client.patch(
            f"/api/v1/processes/{process_id}",
            json={"expected_count": 2, "auto_restart": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["expected_count"] == 2
        assert patch_resp.json()["auto_restart"] is False
        # Otros campos intactos
        assert patch_resp.json()["name"] == "nginx"
        assert patch_resp.json()["pattern"] == "nginx.*master"

        # Eliminar proceso
        del_resp = await client.delete(
            f"/api/v1/processes/{process_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert del_resp.status_code == 204

        # Verificar que ya no existe
        get_after_del = await client.get(
            f"/api/v1/processes/{process_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_after_del.status_code == 404

    @pytest.mark.asyncio
    async def test_create_process_invalid_payload_returns_422(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Payload inválido en create → 422."""
        client = async_client
        token = await _register_and_login(client, "process_owner2@example.com")
        tenant_id = await _get_tenant_id_from_token(client, token)

        server = await _create_server_via_db(db_session, UUID(tenant_id))
        server_id = str(server.id)
        await db_session.commit()

        # name vacío
        resp = await client.post(
            "/api/v1/processes",
            json={
                "server_id": server_id,
                "name": "",  # inválido
                "pattern": "nginx",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

        # pattern vacío
        resp = await client.post(
            "/api/v1/processes",
            json={
                "server_id": server_id,
                "name": "nginx",
                "pattern": "",  # inválido
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

        # expected_count < 1
        resp = await client.post(
            "/api/v1/processes",
            json={
                "server_id": server_id,
                "name": "nginx",
                "pattern": "nginx",
                "expected_count": 0,  # inválido
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_tenant_isolation_processes(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Tenant A no ve procesos de Tenant B."""
        client = async_client
        # Tenant A
        token_a = await _register_and_login(client, "tenanta_proc@example.com")
        tenant_id_a = await _get_tenant_id_from_token(client, token_a)

        server_a = await _create_server_via_db(db_session, UUID(tenant_id_a))
        server_id_a = str(server_a.id)
        await db_session.commit()

        create_a = await client.post(
            "/api/v1/processes",
            json={"server_id": server_id_a, "name": "proc-a", "pattern": "proc-a"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert create_a.status_code == 201
        process_id_a = create_a.json()["id"]

        # Tenant B
        token_b = await _register_and_login(client, "tenantb_proc@example.com")
        tenant_id_b = await _get_tenant_id_from_token(client, token_b)

        server_b = await _create_server_via_db(db_session, UUID(tenant_id_b))
        server_id_b = str(server_b.id)
        await db_session.commit()

        create_b = await client.post(
            "/api/v1/processes",
            json={"server_id": server_id_b, "name": "proc-b", "pattern": "proc-b"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert create_b.status_code == 201
        process_id_b = create_b.json()["id"]

        # A lista sus procesos → solo ve el suyo
        list_a = await client.get(
            "/api/v1/processes",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert list_a.status_code == 200
        processes_a = list_a.json()
        assert len(processes_a) == 1
        assert processes_a[0]["id"] == process_id_a

        # B lista sus procesos → solo ve el suyo
        list_b = await client.get(
            "/api/v1/processes",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert list_b.status_code == 200
        processes_b = list_b.json()
        assert len(processes_b) == 1
        assert processes_b[0]["id"] == process_id_b

        # A intenta GET proceso de B → 404
        cross_get = await client.get(
            f"/api/v1/processes/{process_id_b}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert cross_get.status_code == 404

        # A intenta PATCH proceso de B → 404
        cross_patch = await client.patch(
            f"/api/v1/processes/{process_id_b}",
            json={"name": "hacked"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert cross_patch.status_code == 404

        # A intenta DELETE proceso de B → 404
        cross_del = await client.delete(
            f"/api/v1/processes/{process_id_b}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert cross_del.status_code == 404


# ──────────────────────────────────────────────
# Tests SERVICES
# ──────────────────────────────────────────────
class TestServicesCRUD:
    """Tests CRUD de servicios."""

    @pytest.mark.asyncio
    async def test_create_list_get_patch_delete_service(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """CRUD completo de servicio."""
        client = async_client
        token = await _register_and_login(client, "service_owner@example.com")
        tenant_id = await _get_tenant_id_from_token(client, token)

        # Crear server primero
        server = await _create_server_via_db(db_session, UUID(tenant_id))
        server_id = str(server.id)
        await db_session.commit()

        # Crear servicio
        create_resp = await client.post(
            "/api/v1/services",
            json={
                "server_id": server_id,
                "name": "nginx",
                "desired_state": "running",
                "auto_restart": True,
                "config": {"restart_cmd": "systemctl restart nginx"},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_resp.status_code == 201
        service_data = create_resp.json()
        service_id = service_data["id"]
        assert service_data["name"] == "nginx"
        assert service_data["desired_state"] == "running"
        assert service_data["auto_restart"] is True
        assert service_data["config"] == {"restart_cmd": "systemctl restart nginx"}
        assert service_data["tenant_id"] == tenant_id
        assert service_data["server_id"] == server_id
        assert service_data["last_status"] == "unknown"
        assert service_data["last_checked_at"] is None

        # Listar servicios
        list_resp = await client.get(
            "/api/v1/services",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        services = list_resp.json()
        assert len(services) == 1
        assert services[0]["id"] == service_id

        # Filtrar por server_id
        list_filtered = await client.get(
            f"/api/v1/services?server_id={server_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_filtered.status_code == 200
        assert len(list_filtered.json()) == 1

        # Obtener un servicio
        get_resp = await client.get(
            f"/api/v1/services/{service_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == service_id

        # Actualizar servicio (patch parcial)
        patch_resp = await client.patch(
            f"/api/v1/services/{service_id}",
            json={"desired_state": "stopped", "auto_restart": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["desired_state"] == "stopped"
        assert patch_resp.json()["auto_restart"] is False
        assert patch_resp.json()["name"] == "nginx"

        # Eliminar servicio
        del_resp = await client.delete(
            f"/api/v1/services/{service_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert del_resp.status_code == 204

        # Verificar que ya no existe
        get_after_del = await client.get(
            f"/api/v1/services/{service_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_after_del.status_code == 404

    @pytest.mark.asyncio
    async def test_create_service_invalid_payload_returns_422(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Payload inválido en create → 422."""
        client = async_client
        token = await _register_and_login(client, "service_owner2@example.com")
        tenant_id = await _get_tenant_id_from_token(client, token)

        server = await _create_server_via_db(db_session, UUID(tenant_id))
        server_id = str(server.id)
        await db_session.commit()

        # name vacío
        resp = await client.post(
            "/api/v1/services",
            json={
                "server_id": server_id,
                "name": "",  # inválido
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

        # desired_state inválido
        resp = await client.post(
            "/api/v1/services",
            json={
                "server_id": server_id,
                "name": "nginx",
                "desired_state": "invalid_state",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_tenant_isolation_services(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Tenant A no ve servicios de Tenant B."""
        client = async_client
        # Tenant A
        token_a = await _register_and_login(client, "tenanta_svc@example.com")
        tenant_id_a = await _get_tenant_id_from_token(client, token_a)

        server_a = await _create_server_via_db(db_session, UUID(tenant_id_a))
        server_id_a = str(server_a.id)
        await db_session.commit()

        create_a = await client.post(
            "/api/v1/services",
            json={"server_id": server_id_a, "name": "svc-a"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert create_a.status_code == 201
        service_id_a = create_a.json()["id"]

        # Tenant B
        token_b = await _register_and_login(client, "tenantb_svc@example.com")
        tenant_id_b = await _get_tenant_id_from_token(client, token_b)

        server_b = await _create_server_via_db(db_session, UUID(tenant_id_b))
        server_id_b = str(server_b.id)
        await db_session.commit()

        create_b = await client.post(
            "/api/v1/services",
            json={"server_id": server_id_b, "name": "svc-b"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert create_b.status_code == 201
        service_id_b = create_b.json()["id"]

        # A lista sus servicios → solo ve el suyo
        list_a = await client.get(
            "/api/v1/services",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert list_a.status_code == 200
        services_a = list_a.json()
        assert len(services_a) == 1
        assert services_a[0]["id"] == service_id_a

        # B lista sus servicios → solo ve el suyo
        list_b = await client.get(
            "/api/v1/services",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert list_b.status_code == 200
        services_b = list_b.json()
        assert len(services_b) == 1
        assert services_b[0]["id"] == service_id_b

        # Cross-tenant access → 404
        cross_get = await client.get(
            f"/api/v1/services/{service_id_b}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert cross_get.status_code == 404


# ──────────────────────────────────────────────
# Tests JOBS
# ──────────────────────────────────────────────
class TestJobsCRUD:
    """Tests CRUD de jobs."""

    @pytest.mark.asyncio
    async def test_create_list_get_patch_delete_job(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """CRUD completo de job."""
        client = async_client
        token = await _register_and_login(client, "job_owner@example.com")
        tenant_id = await _get_tenant_id_from_token(client, token)

        # Crear server primero
        server = await _create_server_via_db(db_session, UUID(tenant_id))
        server_id = str(server.id)
        await db_session.commit()

        # Crear job (batch)
        create_resp = await client.post(
            "/api/v1/jobs",
            json={
                "server_id": server_id,
                "name": "backup-daily",
                "kind": "batch",
                "command": "/usr/local/bin/backup.sh",
                "timeout_s": 7200,
                "alert_on_fail": True,
                "auto_restart": False,
                "status": "active",
                "config": {"retention_days": 30},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_resp.status_code == 201
        job_data = create_resp.json()
        job_id = job_data["id"]
        assert job_data["name"] == "backup-daily"
        assert job_data["kind"] == "batch"
        assert job_data["command"] == "/usr/local/bin/backup.sh"
        assert job_data["timeout_s"] == 7200
        assert job_data["alert_on_fail"] is True
        assert job_data["auto_restart"] is False
        assert job_data["status"] == "active"
        assert job_data["config"] == {"retention_days": 30}
        assert job_data["tenant_id"] == tenant_id
        assert job_data["server_id"] == server_id
        assert job_data["schedule_cron"] is None

        # Listar jobs
        list_resp = await client.get(
            "/api/v1/jobs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        jobs = list_resp.json()
        assert len(jobs) == 1
        assert jobs[0]["id"] == job_id

        # Filtrar por server_id
        list_filtered = await client.get(
            f"/api/v1/jobs?server_id={server_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_filtered.status_code == 200
        assert len(list_filtered.json()) == 1

        # Filtrar por status
        list_by_status = await client.get(
            "/api/v1/jobs?status=active",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_by_status.status_code == 200
        assert len(list_by_status.json()) == 1

        # Obtener un job
        get_resp = await client.get(
            f"/api/v1/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == job_id

        # Actualizar job (patch parcial)
        patch_resp = await client.patch(
            f"/api/v1/jobs/{job_id}",
            json={"timeout_s": 3600, "status": "paused"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["timeout_s"] == 3600
        assert patch_resp.json()["status"] == "paused"
        assert patch_resp.json()["name"] == "backup-daily"
        assert patch_resp.json()["kind"] == "batch"

        # Eliminar job
        del_resp = await client.delete(
            f"/api/v1/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert del_resp.status_code == 204

        # Verificar que ya no existe
        get_after_del = await client.get(
            f"/api/v1/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_after_del.status_code == 404

    @pytest.mark.asyncio
    async def test_create_cron_job_requires_schedule_cron(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Job CRON requiere schedule_cron."""
        client = async_client
        token = await _register_and_login(client, "job_cron_owner@example.com")
        tenant_id = await _get_tenant_id_from_token(client, token)

        server = await _create_server_via_db(db_session, UUID(tenant_id))
        server_id = str(server.id)
        await db_session.commit()

        # CRON sin schedule_cron → 422
        resp = await client.post(
            "/api/v1/jobs",
            json={
                "server_id": server_id,
                "name": "cron-job",
                "kind": "cron",
                "command": "echo hello",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

        # CRON con schedule_cron válido → 201
        resp = await client.post(
            "/api/v1/jobs",
            json={
                "server_id": server_id,
                "name": "cron-job",
                "kind": "cron",
                "schedule_cron": "0 2 * * *",
                "command": "echo hello",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["schedule_cron"] == "0 2 * * *"

    @pytest.mark.asyncio
    async def test_create_job_invalid_payload_returns_422(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Payload inválido en create → 422."""
        client = async_client
        token = await _register_and_login(client, "job_owner2@example.com")
        tenant_id = await _get_tenant_id_from_token(client, token)

        server = await _create_server_via_db(db_session, UUID(tenant_id))
        server_id = str(server.id)
        await db_session.commit()

        # name vacío
        resp = await client.post(
            "/api/v1/jobs",
            json={
                "server_id": server_id,
                "name": "",
                "kind": "batch",
                "command": "echo hello",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

        # command vacío
        resp = await client.post(
            "/api/v1/jobs",
            json={
                "server_id": server_id,
                "name": "test",
                "kind": "batch",
                "command": "",  # inválido
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

        # timeout_s < 1
        resp = await client.post(
            "/api/v1/jobs",
            json={
                "server_id": server_id,
                "name": "test",
                "kind": "batch",
                "command": "echo hello",
                "timeout_s": 0,  # inválido
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

        # kind inválido
        resp = await client.post(
            "/api/v1/jobs",
            json={
                "server_id": server_id,
                "name": "test",
                "kind": "invalid_kind",
                "command": "echo hello",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_tenant_isolation_jobs(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Tenant A no ve jobs de Tenant B."""
        client = async_client
        # Tenant A
        token_a = await _register_and_login(client, "tenanta_job@example.com")
        tenant_id_a = await _get_tenant_id_from_token(client, token_a)

        server_a = await _create_server_via_db(db_session, UUID(tenant_id_a))
        server_id_a = str(server_a.id)
        await db_session.commit()

        create_a = await client.post(
            "/api/v1/jobs",
            json={"server_id": server_id_a, "name": "job-a", "kind": "batch", "command": "echo a"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert create_a.status_code == 201
        job_id_a = create_a.json()["id"]

        # Tenant B
        token_b = await _register_and_login(client, "tenantb_job@example.com")
        tenant_id_b = await _get_tenant_id_from_token(client, token_b)

        server_b = await _create_server_via_db(db_session, UUID(tenant_id_b))
        server_id_b = str(server_b.id)
        await db_session.commit()

        create_b = await client.post(
            "/api/v1/jobs",
            json={"server_id": server_id_b, "name": "job-b", "kind": "batch", "command": "echo b"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert create_b.status_code == 201
        job_id_b = create_b.json()["id"]

        # A lista sus jobs → solo ve el suyo
        list_a = await client.get(
            "/api/v1/jobs",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert list_a.status_code == 200
        jobs_a = list_a.json()
        assert len(jobs_a) == 1
        assert jobs_a[0]["id"] == job_id_a

        # B lista sus jobs → solo ve el suyo
        list_b = await client.get(
            "/api/v1/jobs",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert list_b.status_code == 200
        jobs_b = list_b.json()
        assert len(jobs_b) == 1
        assert jobs_b[0]["id"] == job_id_b

        # Cross-tenant access → 404
        cross_get = await client.get(
            f"/api/v1/jobs/{job_id_b}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert cross_get.status_code == 404

        cross_patch = await client.patch(
            f"/api/v1/jobs/{job_id_b}",
            json={"name": "hacked"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert cross_patch.status_code == 404

        cross_del = await client.delete(
            f"/api/v1/jobs/{job_id_b}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert cross_del.status_code == 404


# ──────────────────────────────────────────────
# Tests JOB RUNS (read-only en T1)
# ──────────────────────────────────────────────
class TestJobRuns:
    """Tests de listado de ejecuciones de job."""

    @pytest.mark.asyncio
    async def test_list_job_runs_empty(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Listar runs de job sin ejecuciones → lista vacía."""
        client = async_client
        token = await _register_and_login(client, "jobruns_owner@example.com")
        tenant_id = await _get_tenant_id_from_token(client, token)

        server = await _create_server_via_db(db_session, UUID(tenant_id))
        server_id = str(server.id)
        await db_session.commit()

        create_resp = await client.post(
            "/api/v1/jobs",
            json={"server_id": server_id, "name": "test-job", "kind": "batch", "command": "echo hello"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_resp.status_code == 201
        job_id = create_resp.json()["id"]

        # Listar runs → vacío
        list_resp = await client.get(
            f"/api/v1/jobs/{job_id}/runs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        assert list_resp.json() == []

    @pytest.mark.asyncio
    async def test_list_job_runs_with_data(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Listar runs de job con datos en BD."""
        client = async_client
        token = await _register_and_login(client, "jobruns_owner2@example.com")
        tenant_id = await _get_tenant_id_from_token(client, token)

        server = await _create_server_via_db(db_session, UUID(tenant_id))

        # Crear job en BD directamente
        job_obj = Job(
            tenant_id=UUID(tenant_id),
            server_id=server.id,
            name="test-job-runs",
            kind=JobKind.BATCH,
            command="echo hello",
        )
        db_session.add(job_obj)
        await db_session.flush()
        job_id = str(job_obj.id)

        # Crear JobRuns
        now = datetime.now(UTC)
        run1 = JobRun(
            tenant_id=UUID(tenant_id),
            job_id=job_obj.id,
            started_at=now - timedelta(hours=2),
            finished_at=now - timedelta(hours=2) + timedelta(minutes=5),
            exit_code=0,
            status="success",
            output_tail="backup completed",
            run_metadata={},
        )
        run2 = JobRun(
            tenant_id=UUID(tenant_id),
            job_id=job_obj.id,
            started_at=now - timedelta(hours=1),
            finished_at=now - timedelta(hours=1) + timedelta(minutes=3),
            exit_code=1,
            status="failed",
            output_tail="disk full",
            run_metadata={},
        )
        run3 = JobRun(
            tenant_id=UUID(tenant_id),
            job_id=job_obj.id,
            started_at=now,
            finished_at=None,
            exit_code=None,
            status="running",
            output_tail=None,
            run_metadata={},
        )
        db_session.add_all([run1, run2, run3])
        await db_session.commit()

        # Listar runs → 3 elementos, más recientes primero
        list_resp = await client.get(
            f"/api/v1/jobs/{job_id}/runs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        runs = list_resp.json()
        assert len(runs) == 3
        # Orden: más reciente primero (run3, run2, run1)
        assert runs[0]["status"] == "running"
        assert runs[1]["status"] == "failed"
        assert runs[2]["status"] == "success"
        assert all(r["job_id"] == job_id for r in runs)
        assert all(r["tenant_id"] == tenant_id for r in runs)

    @pytest.mark.asyncio
    async def test_list_job_runs_pagination(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Paginación en listado de runs."""
        client = async_client
        token = await _register_and_login(client, "jobruns_page@example.com")
        tenant_id = await _get_tenant_id_from_token(client, token)

        server = await _create_server_via_db(db_session, UUID(tenant_id))

        job_obj = Job(
            tenant_id=UUID(tenant_id),
            server_id=server.id,
            name="test-job-page",
            kind=JobKind.BATCH,
            command="echo hello",
        )
        db_session.add(job_obj)
        await db_session.flush()
        job_id = str(job_obj.id)

        now = datetime.now(UTC)
        for i in range(5):
            run = JobRun(
                tenant_id=UUID(tenant_id),
                job_id=job_obj.id,
                started_at=now - timedelta(minutes=i * 10),
                finished_at=now - timedelta(minutes=i * 10) + timedelta(minutes=2),
                exit_code=0,
                status="success",
                run_metadata={},
            )
            db_session.add(run)
        await db_session.commit()

        # Primera página
        list_resp = await client.get(
            f"/api/v1/jobs/{job_id}/runs?limit=2&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        runs = list_resp.json()
        assert len(runs) == 2

        # Segunda página
        list_resp2 = await client.get(
            f"/api/v1/jobs/{job_id}/runs?limit=2&offset=2",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp2.status_code == 200
        runs2 = list_resp2.json()
        assert len(runs2) == 2

        # IDs no se repiten
        all_ids = {r["id"] for r in runs} | {r["id"] for r in runs2}
        assert len(all_ids) == 4

    @pytest.mark.asyncio
    async def test_list_job_runs_cross_tenant_returns_404(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Listar runs de job de otro tenant → 404 (job no encontrado)."""
        client = async_client
        # Tenant A crea job
        token_a = await _register_and_login(client, "tenanta_jr@example.com")
        tenant_id_a = await _get_tenant_id_from_token(client, token_a)

        server_a = await _create_server_via_db(db_session, UUID(tenant_id_a))
        job_a = Job(
            tenant_id=UUID(tenant_id_a),
            server_id=server_a.id,
            name="job-a",
            kind=JobKind.BATCH,
            command="echo a",
        )
        db_session.add(job_a)
        await db_session.flush()
        job_id_a = str(job_a.id)
        await db_session.commit()

        # Tenant B
        token_b = await _register_and_login(client, "tenantb_jr@example.com")

        # B intenta listar runs de job de A → 404
        list_resp = await client.get(
            f"/api/v1/jobs/{job_id_a}/runs",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert list_resp.status_code == 404
