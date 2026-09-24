"""Tests para motor de alertas y API (T5).

Cubre: disparo sostenido, no-dedup, resolución automática, CRUD reglas,
ack/resolve vía API, aislamiento por tenant.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.db.session import get_db_session
from app.main import app
from app.models.alert import (
    Alert,
    AlertDelivery,
    AlertOperator,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    EntityType,
)
from app.models.metric import Metric, MetricType
from app.models.server import Server, ServerStatus
from app.models.tenant import Tenant
from app.workers.alerts import evaluate_alerts
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# ──────────────────────────────────────────────
# Helpers de autenticación (patrón test_ingest.py)
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
    return login_resp.json()["access_token"]  # type: ignore[no-any-return]


async def _create_api_key(client: AsyncClient, token: str, name: str) -> str:
    """Crea API key y retorna raw_key."""
    create_resp = await client.post(
        "/auth/api-keys",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201
    return create_resp.json()["raw_key"]  # type: ignore[no-any-return]


async def _create_server_via_api(client: AsyncClient, api_key: str, hostname: str) -> str:
    """Registra un server y retorna su ID."""
    reg_resp = await client.post(
        "/api/v1/servers/register",
        json={"hostname": hostname},
        headers={"X-Api-Key": api_key},
    )
    assert reg_resp.status_code == 201
    return reg_resp.json()["id"]  # type: ignore[no-any-return]


async def _ingest_metrics(client: AsyncClient, api_key: str, server_id: str, metrics: list[dict]) -> None:
    """Ingesta métricas para un server."""
    resp = await client.post(
        "/api/v1/ingest/metrics",
        json={"server_id": server_id, "metrics": metrics},
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 202


# ──────────────────────────────────────────────
# Helpers de BD directa (patrón test_rollups.py)
# ──────────────────────────────────────────────
async def _seed_tenant_server(session: AsyncSession) -> tuple[Tenant, Server]:
    """Crea tenant + server de prueba y devuelve ambos."""
    tenant = Tenant(name="alert-tenant", slug=f"alert-{uuid4().hex[:8]}")
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


class _MetricSeed:
    """Parámetros para _add_metrics (evita PLR0913)."""

    def __init__(
        self,
        server: Server,
        tenant: Tenant,
        metric_type: MetricType,
        values: list[float],
        base_ts: datetime | None = None,
    ) -> None:
        self.server = server
        self.tenant = tenant
        self.metric_type = metric_type
        self.values = values
        self.base_ts = base_ts
        self.interval_seconds = 10


async def _add_metrics(session: AsyncSession, seed: _MetricSeed) -> list[datetime]:
    """Inserta métricas con timestamps consecutivos. Devuelve lista de timestamps usados."""
    if seed.base_ts is None:
        seed.base_ts = datetime.now(UTC) - timedelta(seconds=len(seed.values) * seed.interval_seconds)
    timestamps = []
    for i, value in enumerate(seed.values):
        ts = seed.base_ts + timedelta(seconds=i * seed.interval_seconds)
        session.add(
            Metric(
                ts=ts,
                server_id=seed.server.id,
                tenant_id=seed.tenant.id,
                type=seed.metric_type,
                value=value,
            )
        )
        timestamps.append(ts)
    await session.flush()
    return timestamps


# ──────────────────────────────────────────────
# Tests del MOTOR (unitarios con db_session)
# ──────────────────────────────────────────────
class TestAlertEngine:
    """Tests de evaluate_alerts() — motor de evaluación."""

    async def test_sustained_breach_creates_alert_and_deliveries(
        self, db_session: AsyncSession
    ) -> None:
        """Regla con umbral superado sostenidamente → crea 1 alerta OPEN + deliveries pending."""
        tenant, server = await _seed_tenant_server(db_session)

        # Métricas: 5 muestras > 80% en ventana de 60s (duration_s=60)
        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=60)
        await _add_metrics(
            db_session,
            _MetricSeed(server, tenant, MetricType.CPU_USAGE, [85.0, 87.0, 82.0, 88.0, 90.0], base_ts=window_start),
        )

        # Crear regla: cpu_usage > 80 por 60s
        rule = AlertRule(
            tenant_id=tenant.id,
            entity_type=EntityType.SERVER,
            entity_id=server.id,
            metric="cpu_usage",
            operator=AlertOperator.GT,
            threshold=80.0,
            duration_s=60,
            severity=AlertSeverity.WARNING,
            channels={"email": {}, "webhook": {}},
            is_active=True,
        )
        db_session.add(rule)
        await db_session.flush()

        # Ejecutar motor
        created = await evaluate_alerts(db_session)

        # Verificaciones
        assert created == 1

        alert = await db_session.scalar(
            select(Alert).where(Alert.rule_id == rule.id)
        )
        assert alert is not None
        assert alert.status == AlertStatus.OPEN
        assert alert.severity == AlertSeverity.WARNING
        assert alert.server_id == server.id
        assert alert.tenant_id == tenant.id
        assert alert.triggered_at is not None
        assert alert.resolved_at is None
        assert alert.acknowledged_at is None
        assert alert.value_at_trigger == 90.0  # último valor

        # Verificar deliveries (uno por canal)
        deliveries = (
            await db_session.scalars(
                select(AlertDelivery).where(AlertDelivery.alert_id == alert.id)
            )
        ).all()
        assert len(deliveries) == 2
        channels = {d.channel for d in deliveries}
        assert channels == {"email", "webhook"}
        for d in deliveries:
            assert d.status == "pending"
            assert d.tenant_id == tenant.id

    async def test_sustained_breach_all_samples_must_match(self, db_session: AsyncSession) -> None:
        """Si ALGUNA muestra no cumple, NO dispara (condición sostenida = ALL)."""
        tenant, server = await _seed_tenant_server(db_session)

        # 4 muestras > 80, 1 muestra = 75 (no cumple > 80)
        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=60)
        await _add_metrics(
            db_session,
            _MetricSeed(server, tenant, MetricType.CPU_USAGE, [85.0, 87.0, 75.0, 88.0, 90.0], base_ts=window_start),
        )

        rule = AlertRule(
            tenant_id=tenant.id,
            entity_type=EntityType.SERVER,
            entity_id=server.id,
            metric="cpu_usage",
            operator=AlertOperator.GT,
            threshold=80.0,
            duration_s=60,
            severity=AlertSeverity.WARNING,
            channels={"email": {}},
            is_active=True,
        )
        db_session.add(rule)
        await db_session.flush()

        created = await evaluate_alerts(db_session)

        assert created == 0
        alert = await db_session.scalar(
            select(Alert).where(Alert.rule_id == rule.id)
        )
        assert alert is None

    async def test_no_dedup_while_open_or_acknowledged(self, db_session: AsyncSession) -> None:
        """Misma regla+server no re-dispara mientras exista alerta OPEN/ACK."""
        tenant, server = await _seed_tenant_server(db_session)

        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=60)
        await _add_metrics(
            db_session,
            _MetricSeed(server, tenant, MetricType.CPU_USAGE, [85.0, 87.0, 82.0, 88.0, 90.0], base_ts=window_start),
        )

        rule = AlertRule(
            tenant_id=tenant.id,
            entity_type=EntityType.SERVER,
            entity_id=server.id,
            metric="cpu_usage",
            operator=AlertOperator.GT,
            threshold=80.0,
            duration_s=60,
            severity=AlertSeverity.WARNING,
            channels={"email": {}},
            is_active=True,
        )
        db_session.add(rule)
        await db_session.flush()

        # Primera ejecución → crea alerta
        created1 = await evaluate_alerts(db_session)
        assert created1 == 1

        alert = await db_session.scalar(
            select(Alert).where(Alert.rule_id == rule.id)
        )
        assert alert is not None
        alert_id_1 = alert.id

        # Segunda ejecución con MISMAS métricas → NO crea duplicado
        created2 = await evaluate_alerts(db_session)
        assert created2 == 0

        # Verificar que sigue siendo la misma alerta
        alert2 = await db_session.scalar(
            select(Alert).where(Alert.rule_id == rule.id)
        )
        assert alert2 is not None
        assert alert2.id == alert_id_1
        assert alert2.status == AlertStatus.OPEN

        # Marcar como acknowledged y volver a ejecutar → NO re-dispara
        alert2.status = AlertStatus.ACKNOWLEDGED
        alert2.acknowledged_at = datetime.now(UTC)
        await db_session.flush()

        created3 = await evaluate_alerts(db_session)
        assert created3 == 0

        alert3 = await db_session.scalar(
            select(Alert).where(Alert.rule_id == rule.id)
        )
        assert alert3 is not None
        assert alert3.id == alert_id_1
        assert alert3.status == AlertStatus.ACKNOWLEDGED

    async def test_auto_resolve_when_condition_clears(self, db_session: AsyncSession) -> None:
        """Cuando métrica vuelve a rango, alerta OPEN se marca RESOLVED con resolved_at."""
        tenant, server = await _seed_tenant_server(db_session)

        # Fase 1: métricas altas → dispara alerta
        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=60)
        await _add_metrics(
            db_session,
            _MetricSeed(server, tenant, MetricType.CPU_USAGE, [85.0, 87.0, 82.0, 88.0, 90.0], base_ts=window_start),
        )

        rule = AlertRule(
            tenant_id=tenant.id,
            entity_type=EntityType.SERVER,
            entity_id=server.id,
            metric="cpu_usage",
            operator=AlertOperator.GT,
            threshold=80.0,
            duration_s=60,
            severity=AlertSeverity.WARNING,
            channels={"email": {}},
            is_active=True,
        )
        db_session.add(rule)
        await db_session.flush()

        created1 = await evaluate_alerts(db_session)
        assert created1 == 1

        alert = await db_session.scalar(
            select(Alert).where(Alert.rule_id == rule.id)
        )
        assert alert is not None
        assert alert.status == AlertStatus.OPEN
        assert alert.resolved_at is None

        # Fase 2: métricas vuelven a rango (bajas) → resuelve
        # Usar nueva ventana temporal para nueva evaluación
        now2 = datetime.now(UTC) + timedelta(seconds=70)
        window_start2 = now2 - timedelta(seconds=60)
        await _add_metrics(
            db_session,
            _MetricSeed(server, tenant, MetricType.CPU_USAGE, [45.0, 50.0, 40.0, 55.0, 48.0], base_ts=window_start2),
        )

        created2 = await evaluate_alerts(db_session)
        assert created2 == 0  # no crea nueva

        await db_session.refresh(alert)
        assert alert.status == AlertStatus.RESOLVED
        assert alert.resolved_at is not None

    async def test_rule_applies_to_all_servers_when_entity_id_none(self, db_session: AsyncSession) -> None:
        """Regla con entity_id=None aplica a TODOS los servers del tenant."""
        tenant, server1 = await _seed_tenant_server(db_session)

        # Segundo server mismo tenant
        server2 = Server(
            tenant_id=tenant.id,
            hostname=f"server2-{uuid4().hex[:8]}",
            ip="10.0.0.2",
            os="linux",
            status=ServerStatus.ONLINE,
        )
        db_session.add(server2)
        await db_session.flush()

        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=60)

        # Métricas altas en AMBOS servers
        await _add_metrics(
            db_session,
            _MetricSeed(server1, tenant, MetricType.CPU_USAGE, [85.0, 87.0, 82.0, 88.0, 90.0], base_ts=window_start),
        )
        await _add_metrics(
            db_session,
            _MetricSeed(server2, tenant, MetricType.CPU_USAGE, [83.0, 86.0, 81.0, 89.0, 84.0], base_ts=window_start),
        )

        # Regla SIN entity_id → todos los servers
        rule = AlertRule(
            tenant_id=tenant.id,
            entity_type=EntityType.SERVER,
            entity_id=None,
            metric="cpu_usage",
            operator=AlertOperator.GT,
            threshold=80.0,
            duration_s=60,
            severity=AlertSeverity.WARNING,
            channels={"email": {}},
            is_active=True,
        )
        db_session.add(rule)
        await db_session.flush()

        created = await evaluate_alerts(db_session)

        assert created == 2  # una alerta por server

        alerts = (await db_session.scalars(
            select(Alert).where(Alert.rule_id == rule.id)
        )).all()
        assert len(alerts) == 2
        server_ids = {a.server_id for a in alerts}
        assert server_ids == {server1.id, server2.id}
        for a in alerts:
            assert a.status == AlertStatus.OPEN

    async def test_inactive_rule_is_skipped(self, db_session: AsyncSession) -> None:
        """Regla is_active=False no evalúa."""
        tenant, server = await _seed_tenant_server(db_session)

        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=60)
        await _add_metrics(
            db_session,
            _MetricSeed(server, tenant, MetricType.CPU_USAGE, [95.0, 97.0, 92.0, 98.0, 99.0], base_ts=window_start),
        )

        rule = AlertRule(
            tenant_id=tenant.id,
            entity_type=EntityType.SERVER,
            entity_id=server.id,
            metric="cpu_usage",
            operator=AlertOperator.GT,
            threshold=80.0,
            duration_s=60,
            severity=AlertSeverity.WARNING,
            channels={"email": {}},
            is_active=False,  # INACTIVA
        )
        db_session.add(rule)
        await db_session.flush()

        created = await evaluate_alerts(db_session)
        assert created == 0

        alert = await db_session.scalar(
            select(Alert).where(Alert.rule_id == rule.id)
        )
        assert alert is None

    async def test_no_metrics_in_window_no_eval(self, db_session: AsyncSession) -> None:
        """Sin muestras en ventana → no evalúa (no crea ni resuelve)."""
        tenant, server = await _seed_tenant_server(db_session)

        rule = AlertRule(
            tenant_id=tenant.id,
            entity_type=EntityType.SERVER,
            entity_id=server.id,
            metric="cpu_usage",
            operator=AlertOperator.GT,
            threshold=80.0,
            duration_s=60,
            severity=AlertSeverity.WARNING,
            channels={"email": {}},
            is_active=True,
        )
        db_session.add(rule)
        await db_session.flush()

        created = await evaluate_alerts(db_session)
        assert created == 0

    async def test_multiple_rules_same_server_independent(self, db_session: AsyncSession) -> None:
        """Múltiples reglas en mismo server evalúan independientemente."""
        tenant, server = await _seed_tenant_server(db_session)

        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=60)
        # Métricas que cumplen ambas: > 80 y > 50
        await _add_metrics(
            db_session,
            _MetricSeed(server, tenant, MetricType.CPU_USAGE, [85.0, 87.0, 82.0, 88.0, 90.0], base_ts=window_start),
        )

        # Regla 1: > 80 (warning)
        rule1 = AlertRule(
            tenant_id=tenant.id,
            entity_type=EntityType.SERVER,
            entity_id=server.id,
            metric="cpu_usage",
            operator=AlertOperator.GT,
            threshold=80.0,
            duration_s=60,
            severity=AlertSeverity.WARNING,
            channels={"email": {}},
            is_active=True,
        )
        # Regla 2: > 50 (critical)
        rule2 = AlertRule(
            tenant_id=tenant.id,
            entity_type=EntityType.SERVER,
            entity_id=server.id,
            metric="cpu_usage",
            operator=AlertOperator.GT,
            threshold=50.0,
            duration_s=60,
            severity=AlertSeverity.CRITICAL,
            channels={"webhook": {}},
            is_active=True,
        )
        db_session.add_all([rule1, rule2])
        await db_session.flush()

        created = await evaluate_alerts(db_session)
        assert created == 2

        alerts = (await db_session.scalars(
            select(Alert).where(Alert.rule_id.in_([rule1.id, rule2.id]))
        )).all()
        assert len(alerts) == 2
        severities = {a.severity for a in alerts}
        assert severities == {AlertSeverity.WARNING, AlertSeverity.CRITICAL}


# ──────────────────────────────────────────────
# Tests de API CRUD REGLAS (con async_client)
# ──────────────────────────────────────────────
class TestAlertRulesAPI:
    """Tests CRUD de reglas vía HTTP."""

    @pytest.mark.asyncio
    async def test_create_list_get_patch_delete_rule(self, async_client: AsyncClient) -> None:
        """CRUD completo de regla de alerta."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token = await _register_and_login(client, "alert_owner@example.com")

            # Crear regla
            create_resp = await client.post(
                "/api/v1/alerts/rules",
                json={
                    "entity_type": "server",
                    "entity_id": None,
                    "metric": "cpu_usage",
                    "operator": "gt",
                    "threshold": 80.0,
                    "duration_s": 60,
                    "severity": "warning",
                    "channels": {"email": {}, "webhook": {}},
                    "is_active": True,
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert create_resp.status_code == 201
            rule_data = create_resp.json()
            rule_id = rule_data["id"]
            assert rule_data["metric"] == "cpu_usage"
            assert rule_data["operator"] == "gt"
            assert rule_data["threshold"] == 80.0
            assert rule_data["severity"] == "warning"
            assert rule_data["channels"] == {"email": {}, "webhook": {}}
            assert rule_data["is_active"] is True

            # Listar reglas
            list_resp = await client.get(
                "/api/v1/alerts/rules",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert list_resp.status_code == 200
            rules = list_resp.json()
            assert len(rules) == 1
            assert rules[0]["id"] == rule_id

            # Obtener una regla
            get_resp = await client.get(
                f"/api/v1/alerts/rules/{rule_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert get_resp.status_code == 200
            assert get_resp.json()["id"] == rule_id

            # Actualizar regla (patch parcial)
            patch_resp = await client.patch(
                f"/api/v1/alerts/rules/{rule_id}",
                json={"threshold": 85.0, "severity": "critical"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert patch_resp.status_code == 200
            assert patch_resp.json()["threshold"] == 85.0
            assert patch_resp.json()["severity"] == "critical"
            # Otros campos intactos
            assert patch_resp.json()["metric"] == "cpu_usage"

            # Eliminar regla
            del_resp = await client.delete(
                f"/api/v1/alerts/rules/{rule_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert del_resp.status_code == 204

            # Verificar que ya no existe
            get_after_del = await client.get(
                f"/api/v1/alerts/rules/{rule_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert get_after_del.status_code == 404

    @pytest.mark.asyncio
    async def test_create_rule_invalid_payload_returns_422(self, async_client: AsyncClient) -> None:
        """Payload inválido en create → 422."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token = await _register_and_login(client, "alert_owner2@example.com")

            # metric vacío
            resp = await client.post(
                "/api/v1/alerts/rules",
                json={
                    "entity_type": "server",
                    "metric": "",  # inválido
                    "operator": "gt",
                    "threshold": 80.0,
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 422

            # operator inválido
            resp = await client.post(
                "/api/v1/alerts/rules",
                json={
                    "entity_type": "server",
                    "metric": "cpu_usage",
                    "operator": "invalid_op",
                    "threshold": 80.0,
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_tenant_isolation_rules(self, async_client: AsyncClient) -> None:
        """Tenant A no ve reglas de Tenant B."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Tenant A
            token_a = await _register_and_login(client, "tenanta@example.com")
            create_a = await client.post(
                "/api/v1/alerts/rules",
                json={
                    "entity_type": "server",
                    "metric": "cpu_usage",
                    "operator": "gt",
                    "threshold": 80.0,
                },
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert create_a.status_code == 201
            rule_id_a = create_a.json()["id"]

            # Tenant B
            token_b = await _register_and_login(client, "tenantb@example.com")
            create_b = await client.post(
                "/api/v1/alerts/rules",
                json={
                    "entity_type": "server",
                    "metric": "mem_usage",
                    "operator": "gt",
                    "threshold": 90.0,
                },
                headers={"Authorization": f"Bearer {token_b}"},
            )
            assert create_b.status_code == 201
            rule_id_b = create_b.json()["id"]

            # A lista sus reglas → solo ve la suya
            list_a = await client.get(
                "/api/v1/alerts/rules",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert list_a.status_code == 200
            rules_a = list_a.json()
            assert len(rules_a) == 1
            assert rules_a[0]["id"] == rule_id_a

            # B lista sus reglas → solo ve la suya
            list_b = await client.get(
                "/api/v1/alerts/rules",
                headers={"Authorization": f"Bearer {token_b}"},
            )
            assert list_b.status_code == 200
            rules_b = list_b.json()
            assert len(rules_b) == 1
            assert rules_b[0]["id"] == rule_id_b

            # A intenta GET regla de B → 404
            cross_get = await client.get(
                f"/api/v1/alerts/rules/{rule_id_b}",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert cross_get.status_code == 404

            # A intenta PATCH regla de B → 404
            cross_patch = await client.patch(
                f"/api/v1/alerts/rules/{rule_id_b}",
                json={"threshold": 95.0},
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert cross_patch.status_code == 404

            # A intenta DELETE regla de B → 404
            cross_del = await client.delete(
                f"/api/v1/alerts/rules/{rule_id_b}",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert cross_del.status_code == 404


# ──────────────────────────────────────────────
# Tests de API ALERTAS (list, ack, resolve)
# ──────────────────────────────────────────────
class TestAlertsAPI:
    """Tests de ciclo de vida de alertas vía HTTP."""

    async def _setup_alert_via_engine(
        self, client: AsyncClient, token: str, api_key: str
    ) -> tuple[str, str]:
        """Helper: crea server, ingiere métricas altas, crea regla, ejecuta motor → retorna (rule_id, alert_id)."""
        # Registrar server
        server_id = await _create_server_via_api(client, api_key, "alert-test-server")

        # Ingerir métricas altas sostenidas
        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=60)
        metrics = [
            {"type": "cpu_usage", "value": 85.0, "ts": (window_start + timedelta(seconds=i * 10)).isoformat()}
            for i in range(5)
        ]
        await _ingest_metrics(client, api_key, server_id, metrics)

        # Crear regla via API
        create_rule = await client.post(
            "/api/v1/alerts/rules",
            json={
                "entity_type": "server",
                "entity_id": server_id,
                "metric": "cpu_usage",
                "operator": "gt",
                "threshold": 80.0,
                "duration_s": 60,
                "severity": "warning",
                "channels": {"email": {}},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_rule.status_code == 201
        rule_id = create_rule.json()["id"]

        # Ejecutar motor directamente (bypass cron)
        async with get_db_session() as session:
            created = await evaluate_alerts(session)
            assert created == 1
            alert = await session.scalar(
                select(Alert).where(Alert.rule_id == UUID(rule_id))
            )
            assert alert is not None
            alert_id = str(alert.id)

        return rule_id, alert_id

    @pytest.mark.asyncio
    async def test_list_alerts_with_filters(self, async_client: AsyncClient) -> None:
        """GET /alerts con filtros status, severity, rule_id."""
        client = async_client
        token = await _register_and_login(client, "alert_list_owner@example.com")
        api_key = await _create_api_key(client, token, "Agent Alert")

        rule_id, alert_id = await self._setup_alert_via_engine(client, token, api_key)

        # Listar todas
        list_resp = await client.get(
            "/api/v1/alerts",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        alerts = list_resp.json()
        assert len(alerts) == 1
        assert alerts[0]["id"] == alert_id
        assert alerts[0]["status"] == "open"
        assert alerts[0]["severity"] == "warning"

        # Filtrar por status=open
        list_open = await client.get(
            "/api/v1/alerts?status=open",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_open.status_code == 200
        assert len(list_open.json()) == 1

        # Filtrar por status=resolved → vacío
        list_resolved = await client.get(
            "/api/v1/alerts?status=resolved",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resolved.status_code == 200
        assert len(list_resolved.json()) == 0

        # Filtrar por severity
        list_warn = await client.get(
            "/api/v1/alerts?severity=warning",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_warn.status_code == 200
        assert len(list_warn.json()) == 1

        list_crit = await client.get(
            "/api/v1/alerts?severity=critical",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_crit.status_code == 200
        assert len(list_crit.json()) == 0

        # Filtrar por rule_id
        list_by_rule = await client.get(
            f"/api/v1/alerts?rule_id={rule_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_by_rule.status_code == 200
        assert len(list_by_rule.json()) == 1

        # Paginación
        list_page = await client.get(
            "/api/v1/alerts?limit=1&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_page.status_code == 200
        assert len(list_page.json()) == 1

    @pytest.mark.asyncio
    async def test_ack_alert_marks_acknowledged(self, async_client: AsyncClient) -> None:
        """POST /alerts/{id}/ack marca acknowledged + acknowledged_at."""
        client = async_client
        token = await _register_and_login(client, "alert_ack_owner@example.com")
        api_key = await _create_api_key(client, token, "Agent Ack")

        rule_id, alert_id = await self._setup_alert_via_engine(client, token, api_key)

        # Ack - use a valid UUID for acknowledged_by
        ack_resp = await client.post(
            f"/api/v1/alerts/{alert_id}/ack",
            json={"acknowledged_by": str(uuid4())},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ack_resp.status_code == 200
        ack_data = ack_resp.json()
        assert ack_data["id"] == alert_id
        assert ack_data["status"] == "acknowledged"
        assert ack_data["acknowledged_at"] is not None
        assert ack_data["resolved_at"] is None
        assert ack_data["acknowledged_by"] is not None

        # Verificar en list
        list_resp = await client.get(
            "/api/v1/alerts",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.json()[0]["status"] == "acknowledged"

    @pytest.mark.asyncio
    async def test_resolve_alert_marks_resolved(self, async_client: AsyncClient) -> None:
        """POST /alerts/{id}/resolve marca resolved + resolved_at."""
        client = async_client
        token = await _register_and_login(client, "alert_resolve_owner@example.com")
        api_key = await _create_api_key(client, token, "Agent Resolve")

        rule_id, alert_id = await self._setup_alert_via_engine(client, token, api_key)

        # Resolve
        resolve_resp = await client.post(
            f"/api/v1/alerts/{alert_id}/resolve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resolve_resp.status_code == 200
        resolve_data = resolve_resp.json()
        assert resolve_data["id"] == alert_id
        assert resolve_data["status"] == "resolved"
        assert resolve_data["resolved_at"] is not None
        assert resolve_data["acknowledged_at"] is None
        assert resolve_data["acknowledged_by"] is None

        # Verificar en list
        list_resp = await client.get(
            "/api/v1/alerts",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.json()[0]["status"] == "resolved"

    @pytest.mark.asyncio
    async def test_ack_then_resolve_works(self, async_client: AsyncClient) -> None:
        """Ack seguido de resolve funciona (ack → resolved)."""
        client = async_client
        token = await _register_and_login(client, "alert_ack_resolve@example.com")
        api_key = await _create_api_key(client, token, "Agent AR")

        rule_id, alert_id = await self._setup_alert_via_engine(client, token, api_key)

        # Ack
        await client.post(
            f"/api/v1/alerts/{alert_id}/ack",
            json={"acknowledged_by": str(uuid4())},
            headers={"Authorization": f"Bearer {token}"},
        )

        # Resolve
        resolve_resp = await client.post(
            f"/api/v1/alerts/{alert_id}/resolve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resolve_resp.status_code == 200
        assert resolve_resp.json()["status"] == "resolved"
        # acknowledged_at se mantiene
        assert resolve_resp.json()["acknowledged_at"] is not None

    @pytest.mark.asyncio
    async def test_ack_nonexistent_returns_404(self, async_client: AsyncClient) -> None:
        """ACK de alerta inexistente → 404."""
        client = async_client
        token = await _register_and_login(client, "alert_404_owner@example.com")

        fake_id = str(uuid4())
        ack_resp = await client.post(
            f"/api/v1/alerts/{fake_id}/ack",
            json={"acknowledged_by": str(uuid4())},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ack_resp.status_code == 404
        assert ack_resp.json()["detail"] == "Alerta no encontrada"

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_returns_404(self, async_client: AsyncClient) -> None:
        """RESOLVE de alerta inexistente → 404."""
        client = async_client
        token = await _register_and_login(client, "alert_404_owner2@example.com")

        fake_id = str(uuid4())
        resolve_resp = await client.post(
            f"/api/v1/alerts/{fake_id}/resolve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resolve_resp.status_code == 404
        assert resolve_resp.json()["detail"] == "Alerta no encontrada"

    @pytest.mark.asyncio
    async def test_tenant_isolation_alerts(self, async_client: AsyncClient) -> None:
        """Tenant A no ve alertas de Tenant B."""
        client = async_client
        # Tenant A: crear alerta
        token_a = await _register_and_login(client, "tenanta_alert@example.com")
        api_key_a = await _create_api_key(client, token_a, "Agent A")
        rule_id_a, alert_id_a = await self._setup_alert_via_engine(client, token_a, api_key_a)

        # Tenant B: crear alerta
        token_b = await _register_and_login(client, "tenantb_alert@example.com")
        api_key_b = await _create_api_key(client, token_b, "Agent B")
        rule_id_b, alert_id_b = await self._setup_alert_via_engine(client, token_b, api_key_b)

        # A lista → solo su alerta
        list_a = await client.get(
            "/api/v1/alerts",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert list_a.status_code == 200
        alerts_a = list_a.json()
        assert len(alerts_a) == 1
        assert alerts_a[0]["id"] == alert_id_a

        # B lista → solo su alerta
        list_b = await client.get(
            "/api/v1/alerts",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert list_b.status_code == 200
        alerts_b = list_b.json()
        assert len(alerts_b) == 1
        assert alerts_b[0]["id"] == alert_id_b

        # A intenta ack alerta de B → 404
        cross_ack = await client.post(
            f"/api/v1/alerts/{alert_id_b}/ack",
            json={"acknowledged_by": str(uuid4())},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert cross_ack.status_code == 404

        # A intenta resolve alerta de B → 404
        cross_resolve = await client.post(
            f"/api/v1/alerts/{alert_id_b}/resolve",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert cross_resolve.status_code == 404
