"""Tests para ingesta de estado de entidades (T4).

Cubre: services (last_status, last_checked_at), processes (last_count, last_checked_at),
matching semÃ¡ntica, edge cases (404, no configs, regex invÃ¡lido, estado invÃ¡lido).
"""

from uuid import UUID, uuid4

import pytest
from app.models.process import Process
from app.models.process import Process as ProcessModel
from app.models.service import Service, ServiceState
from app.models.service import Service as ServiceModel
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Helpers
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


async def _get_tenant_id_from_token(client: AsyncClient, token: str) -> str:
    """Obtiene el tenant_id del usuario autenticado vÃ­a /auth/me."""
    me_resp = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    return me_resp.json()["tenant_id"]


async def _seed_processes_services(
    db_session: AsyncSession, tenant_id: UUID, server_id: str
) -> tuple[list[Process], list[Service]]:
    """Crea procesos y servicios de prueba en BD."""
    server_uuid = UUID(server_id)
    processes = [
        Process(
            tenant_id=tenant_id,
            server_id=server_uuid,
            name="nginx",
            pattern=r"nginx.*",
            expected_count=1,
            auto_restart=False,
        ),
        Process(
            tenant_id=tenant_id,
            server_id=server_uuid,
            name="redis",
            pattern=r"redis-server.*",
            expected_count=1,
            auto_restart=False,
        ),
        Process(
            tenant_id=tenant_id,
            server_id=server_uuid,
            name="postgres",
            pattern=r"postgres.*",
            expected_count=1,
            auto_restart=False,
        ),
    ]
    for p in processes:
        db_session.add(p)
    await db_session.flush()

    services = [
        Service(
            tenant_id=tenant_id,
            server_id=server_uuid,
            name="nginx",
            desired_state=ServiceState.RUNNING,
            auto_restart=False,
        ),
        Service(
            tenant_id=tenant_id,
            server_id=server_uuid,
            name="redis",
            desired_state=ServiceState.RUNNING,
            auto_restart=False,
        ),
        Service(
            tenant_id=tenant_id,
            server_id=server_uuid,
            name="postgresql",
            desired_state=ServiceState.RUNNING,
            auto_restart=False,
        ),
    ]
    for s in services:
        db_session.add(s)
    await db_session.commit()

    return processes, services


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Tests
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestIngestEntities:
    """Tests para POST /api/v1/ingest/entities."""

    @pytest.mark.asyncio
    async def test_ingest_entities_happy_path(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Happy path: server existe, configs existen, estado se actualiza."""
        client = async_client
        token = await _register_and_login(client, "owner1@example.com")
        api_key = await _create_api_key(client, token, "Agent 1")

        server_id = await _create_server_via_api(client, api_key, "test-server-1")

        # Seed configs en BD
        tenant_id = UUID(await _get_tenant_id_from_token(client, token))
        await _seed_processes_services(db_session, tenant_id, server_id)

        # Ingestar entidades
        ingest_resp = await client.post(
            "/api/v1/ingest/entities",
            json={
                "server_id": server_id,
                "processes": [
                    {"name": "nginx", "cmdline": "nginx: master process", "state": "running"},
                    {"name": "redis", "cmdline": "redis-server *:6379", "state": "running"},
                    {"name": "postgres", "cmdline": "postgres -c config", "state": "running"},
                ],
                "services": [
                    {"name": "nginx", "state": "running"},
                    {"name": "redis", "state": "stopped"},
                    {"name": "postgresql", "state": "running"},
                ],
            },
            headers={"X-Api-Key": api_key},
        )
        assert ingest_resp.status_code == 202
        data = ingest_resp.json()
        assert data["received_processes"] == 3
        assert data["received_services"] == 3
        assert data["matched_processes"] == 3
        assert data["matched_services"] == 3
        assert data["server_id"] == server_id

        # Verificar BD: services last_status actualizado
        db_session.expire_all()  # forzar refresh: la API escribiÃ³ en otra sesiÃ³n
        async with db_session.begin():
            result = await db_session.execute(
                select(ServiceModel).where(ServiceModel.server_id == UUID(server_id))
            )
            services = result.scalars().all()
            assert len(services) == 3
            svc_map = {s.name: s for s in services}
            assert svc_map["nginx"].last_status == ServiceState.RUNNING
            assert svc_map["redis"].last_status == ServiceState.STOPPED
            assert svc_map["postgresql"].last_status == ServiceState.RUNNING
            for s in services:
                assert s.last_checked_at is not None

            # Verificar BD: processes last_count actualizado
            result = await db_session.execute(
                select(ProcessModel).where(ProcessModel.server_id == UUID(server_id))
            )
            processes = result.scalars().all()
            assert len(processes) == 3
            proc_map = {p.name: p for p in processes}
            assert proc_map["nginx"].last_count == 1
            assert proc_map["redis"].last_count == 1
            assert proc_map["postgres"].last_count == 1
            for p in processes:
                assert p.last_checked_at is not None

    @pytest.mark.asyncio
    async def test_ingest_entities_404_unknown_server(
        self, async_client: AsyncClient
    ) -> None:
        """Server desconocido -> 404."""
        client = async_client
        token = await _register_and_login(client, "owner2@example.com")
        api_key = await _create_api_key(client, token, "Agent 2")

        fake_id = str(uuid4())
        resp = await client.post(
            "/api/v1/ingest/entities",
            json={"server_id": fake_id, "processes": [], "services": []},
            headers={"X-Api-Key": api_key},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Server no encontrado"

    @pytest.mark.asyncio
    async def test_ingest_entities_no_configs_returns_zero_matched(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Server sin configs -> 202 con matched=0."""
        client = async_client
        token = await _register_and_login(client, "owner3@example.com")
        api_key = await _create_api_key(client, token, "Agent 3")

        server_id = await _create_server_via_api(client, api_key, "test-server-3")

        # No se crean configs en BD
        resp = await client.post(
            "/api/v1/ingest/entities",
            json={
                "server_id": server_id,
                "processes": [{"name": "nginx", "state": "running"}],
                "services": [{"name": "nginx", "state": "running"}],
            },
            headers={"X-Api-Key": api_key},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["received_processes"] == 1
        assert data["received_services"] == 1
        assert data["matched_processes"] == 0
        assert data["matched_services"] == 0

    @pytest.mark.asyncio
    async def test_ingest_entities_cross_tenant_404(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Cross-tenant -> 404 (server de otro tenant)."""
        client = async_client
        token_a = await _register_and_login(client, "ownera@example.com")
        api_key_a = await _create_api_key(client, token_a, "Agent A")

        server_id_a = await _create_server_via_api(client, api_key_a, "server-a")

        # Seed configs para tenant A
        tenant_id_a = UUID(await _get_tenant_id_from_token(client, token_a))
        await _seed_processes_services(db_session, tenant_id_a, server_id_a)

        # Tenant B intenta ingestar al server de tenant A
        token_b = await _register_and_login(client, "ownerb@example.com")
        api_key_b = await _create_api_key(client, token_b, "Agent B")

        resp = await client.post(
            "/api/v1/ingest/entities",
            json={
                "server_id": server_id_a,
                "processes": [{"name": "nginx", "state": "running"}],
                "services": [],
            },
            headers={"X-Api-Key": api_key_b},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Server no encontrado"

    @pytest.mark.asyncio
    async def test_ingest_entities_invalid_regex_logged_not_crash(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Regex invÃ¡lido en config -> no crash, el config vÃ¡lido igual se procesa."""
        client = async_client
        token = await _register_and_login(client, "owner4@example.com")
        api_key = await _create_api_key(client, token, "Agent 4")

        server_id = await _create_server_via_api(client, api_key, "test-server-4")
        tenant_id = UUID(await _get_tenant_id_from_token(client, token))
        server_uuid = UUID(server_id)

        # Crear proceso con regex invÃ¡lido y uno vÃ¡lido
        invalid_proc = Process(
            tenant_id=tenant_id,
            server_id=server_uuid,
            name="bad-regex",
            pattern="[invalid",  # regex invÃ¡lido
            expected_count=1,
        )
        valid_proc = Process(
            tenant_id=tenant_id,
            server_id=server_uuid,
            name="nginx",
            pattern=r"nginx.*",
            expected_count=1,
        )
        db_session.add_all([invalid_proc, valid_proc])
        await db_session.commit()

        resp = await client.post(
                "/api/v1/ingest/entities",
                json={
                    "server_id": server_id,
                    "processes": [
                        {"name": "nginx", "cmdline": "nginx: master", "state": "running"},
                        {"name": "other", "cmdline": "something", "state": "running"},
                    ],
                    "services": [],
                },
                headers={"X-Api-Key": api_key},
            )
        assert resp.status_code == 202
        data = resp.json()
        # El regex invÃ¡lido no frena el request; el config vÃ¡lido se procesa
        assert data["matched_processes"] == 2  # bad-regex (count 0) + nginx (count 1)

        # Verificar BD: nginx quedÃ³ actualizado; bad-regex no crasheÃ³
        db_session.expire_all()
        async with db_session.begin():
            result = await db_session.execute(
                select(ProcessModel).where(ProcessModel.server_id == UUID(server_id))
            )
            procs = result.scalars().all()
            proc_map = {p.name: p for p in procs}
            assert proc_map["bad-regex"].last_count == 0
            assert proc_map["nginx"].last_count == 1
            assert proc_map["nginx"].last_checked_at is not None

    @pytest.mark.asyncio
    async def test_ingest_entities_service_state_mapping(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Estados de servicio: running/stopped/failed/unknown mapeados correctamente."""
        client = async_client
        token = await _register_and_login(client, "owner5@example.com")
        api_key = await _create_api_key(client, token, "Agent 5")

        server_id = await _create_server_via_api(client, api_key, "test-server-5")
        tenant_id = UUID(await _get_tenant_id_from_token(client, token))
        server_uuid = UUID(server_id)

        # Seed service
        svc = Service(
            tenant_id=tenant_id,
            server_id=server_uuid,
            name="test-svc",
            desired_state=ServiceState.RUNNING,
        )
        db_session.add(svc)
        await db_session.commit()

        # Test mapeo de estados
        test_cases = [
            ("running", ServiceState.RUNNING),
            ("stopped", ServiceState.STOPPED),
            ("failed", ServiceState.FAILED),
            ("invalid_state", ServiceState.UNKNOWN),  # invÃ¡lido -> UNKNOWN
        ]

        for reported, expected in test_cases:
            resp = await client.post(
                "/api/v1/ingest/entities",
                json={
                    "server_id": server_id,
                    "processes": [],
                    "services": [{"name": "test-svc", "state": reported}],
                },
                headers={"X-Api-Key": api_key},
            )
            assert resp.status_code == 202

            # Forzar refresh: la API escribiÃ³ en otra sesiÃ³n
            db_session.expire_all()
            async with db_session.begin():
                result = await db_session.execute(
                    select(ServiceModel).where(ServiceModel.server_id == UUID(server_id))
                )
                svc = result.scalar_one()
                assert svc.last_status == expected
                assert svc.last_checked_at is not None

    @pytest.mark.asyncio
    async def test_ingest_entities_process_regex_matching(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Process regex matching: pattern matches name OR cmdline."""
        client = async_client
        token = await _register_and_login(client, "owner6@example.com")
        api_key = await _create_api_key(client, token, "Agent 6")

        server_id = await _create_server_via_api(client, api_key, "test-server-6")
        tenant_id = UUID(await _get_tenant_id_from_token(client, token))
        server_uuid = UUID(server_id)

        # Proceso config: pattern "nginx.*" debe match name="nginx" y cmdline
        proc1 = Process(
            tenant_id=tenant_id,
            server_id=server_uuid,
            name="nginx-master",
            pattern=r"nginx.*",
            expected_count=2,
        )
        # Proceso config: pattern "redis" match solo por cmdline
        proc2 = Process(
            tenant_id=tenant_id,
            server_id=server_uuid,
            name="redis-worker",
            pattern=r"redis",
            expected_count=1,
        )
        db_session.add_all([proc1, proc2])
        await db_session.commit()

        resp = await client.post(
            "/api/v1/ingest/entities",
            json={
                "server_id": server_id,
                "processes": [
                    {"name": "nginx", "cmdline": "nginx: master process", "state": "running"},
                    {"name": "other", "cmdline": "redis-server *:6379", "state": "running"},
                    {"name": "unrelated", "cmdline": "something-else", "state": "running"},
                ],
                "services": [],
            },
            headers={"X-Api-Key": api_key},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["matched_processes"] == 2

        # Verificar last_count en BD
        db_session.expire_all()
        async with db_session.begin():
            result = await db_session.execute(
                select(ProcessModel).where(ProcessModel.server_id == UUID(server_id))
            )
            procs = result.scalars().all()
            proc_map = {p.name: p for p in procs}
            assert proc_map["nginx-master"].last_count == 1  # match por name ("nginx")
            assert proc_map["redis-worker"].last_count == 1  # match por cmdline ("redis-server *:6379")

    @pytest.mark.asyncio
    async def test_ingest_entities_empty_arrays(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Arrays vacÃ­os -> 202 con 0 received/matched."""
        client = async_client
        token = await _register_and_login(client, "owner7@example.com")
        api_key = await _create_api_key(client, token, "Agent 7")

        server_id = await _create_server_via_api(client, api_key, "test-server-7")

        resp = await client.post(
            "/api/v1/ingest/entities",
            json={"server_id": server_id, "processes": [], "services": []},
            headers={"X-Api-Key": api_key},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["received_processes"] == 0
        assert data["received_services"] == 0
        assert data["matched_processes"] == 0
        assert data["matched_services"] == 0

    @pytest.mark.asyncio
    async def test_ingest_entities_missing_arrays_optional(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Campos opcionales omitidos -> default a array vacÃ­o."""
        client = async_client
        token = await _register_and_login(client, "owner8@example.com")
        api_key = await _create_api_key(client, token, "Agent 8")

        server_id = await _create_server_via_api(client, api_key, "test-server-8")

        # Solo processes, sin services
        resp = await client.post(
            "/api/v1/ingest/entities",
            json={"server_id": server_id, "processes": [{"name": "nginx", "state": "running"}]},
            headers={"X-Api-Key": api_key},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["received_processes"] == 1
        assert data["received_services"] == 0  # default empty

        # Solo services, sin processes
        resp2 = await client.post(
            "/api/v1/ingest/entities",
            json={"server_id": server_id, "services": [{"name": "nginx", "state": "running"}]},
            headers={"X-Api-Key": api_key},
        )
        assert resp2.status_code == 202
        data2 = resp2.json()
        assert data2["received_processes"] == 0
        assert data2["received_services"] == 1

    @pytest.mark.asyncio
    async def test_ingest_entities_process_last_count_zero_when_no_match(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Proceso config sin matches -> last_count=0, last_checked_at actualizado."""
        client = async_client
        token = await _register_and_login(client, "owner9@example.com")
        api_key = await _create_api_key(client, token, "Agent 9")

        server_id = await _create_server_via_api(client, api_key, "test-server-9")
        tenant_id = UUID(await _get_tenant_id_from_token(client, token))
        server_uuid = UUID(server_id)

        # Config con pattern que NO match nada
        proc = Process(
            tenant_id=tenant_id,
            server_id=server_uuid,
            name="nginx",
            pattern=r"apache.*",
            expected_count=1,
        )
        db_session.add(proc)
        await db_session.commit()

        resp = await client.post(
            "/api/v1/ingest/entities",
            json={
                "server_id": server_id,
                "processes": [
                    {"name": "nginx", "cmdline": "nginx: master", "state": "running"}
                ],
                "services": [],
            },
            headers={"X-Api-Key": api_key},
        )
        assert resp.status_code == 202

        # Verificar BD: last_count=0, last_checked_at actualizado
        db_session.expire_all()
        async with db_session.begin():
            result = await db_session.execute(
                select(ProcessModel).where(ProcessModel.server_id == UUID(server_id))
            )
            proc = result.scalar_one()
            assert proc.last_count == 0
            assert proc.last_checked_at is not None
