"""Tests para generadores de reportes (T2 - Mes 5).

Cubre: generate_availability, generate_incidents, generate_alerts, generate_sla, generate_metrics.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.models.alert import Alert, AlertOperator, AlertRule, AlertSeverity, AlertStatus, EntityType
from app.models.metric import Metric, MetricType
from app.models.metric_rollup import MetricRollup, RollupPeriod
from app.models.server import Server, ServerStatus
from app.models.tenant import Tenant
from app.reports.generators import (
    generate_alerts,
    generate_availability,
    generate_incidents,
    generate_metrics,
    generate_report,
    generate_sla,
)
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

async def _setup_tenant_with_server(
    db_session: AsyncSession,
) -> tuple[UUID, UUID]:
    """Crea tenant + server vía API y retorna (tenant_id, server_id)."""
    client = AsyncClient(base_url="http://test")
    # Usar los mismos helpers que otros tests

    # No podemos usar client directo aquí, usamos BD directa
    tenant = Tenant(
        name="Test Tenant",
        slug=f"test-{uuid4().hex[:8]}",
        settings={"sla": {"default_target_pct": 99.9}},
    )
    db_session.add(tenant)
    await db_session.flush()

    server = Server(
        tenant_id=tenant.id,
        hostname=f"server-{uuid4().hex[:8]}",
        ip="10.0.0.1",
        os="linux",
        status=ServerStatus.ONLINE,
        last_heartbeat_at=datetime.now(UTC),
    )
    db_session.add(server)
    await db_session.flush()
    await db_session.commit()

    return tenant.id, server.id


async def _create_metrics(
    db_session: AsyncSession,
    tenant_id: UUID,
    server_id: UUID,
    period_start: datetime,
    period_end: datetime,
    interval_seconds: int = 60,
    gap_at: datetime | None = None,
    gap_duration: timedelta | None = None,
) -> None:
    """Crea métricas simuladas (heartbeats) con gap opcional."""
    current = period_start
    while current <= period_end:
        if gap_at and gap_at <= current < gap_at + (gap_duration or timedelta(0)):
            current += gap_duration or timedelta(minutes=5)
            continue

        metric = Metric(
            tenant_id=tenant_id,
            server_id=server_id,
            ts=current,
            type=MetricType.CPU_USAGE,
            value=50.0,
        )
        db_session.add(metric)
        current += timedelta(seconds=interval_seconds)
    await db_session.commit()


async def _create_alert_rule(
    db_session: AsyncSession,
    tenant_id: UUID,
    entity_type: EntityType = EntityType.SERVER,
    severity: AlertSeverity = AlertSeverity.WARNING,
) -> AlertRule:
    """Crea regla de alerta de prueba."""
    rule = AlertRule(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=None,
        metric="cpu_usage",
        operator=AlertOperator.GTE,
        threshold=80.0,
        duration_s=60,
        severity=severity,
        channels={"email": {"to": ["test@example.com"]}},
        is_active=True,
    )
    db_session.add(rule)
    await db_session.flush()
    return rule


async def _create_alerts_sequence(
    db_session: AsyncSession,
    tenant_id: UUID,
    rule_id: UUID,
    period_start: datetime,
    period_end: datetime,
    count: int = 5,
    interval_minutes: int = 10,
    resolved: bool = False,
    severity: AlertSeverity | None = None,
) -> list[Alert]:
    """Crea secuencia de alertas para testear incidentes."""
    # Si no se pasa severity, obtenerla de la regla
    if severity is None:
        from app.models.alert import AlertRule
        rule_stmt = select(AlertRule).where(AlertRule.id == rule_id)
        rule_result = await db_session.execute(rule_stmt)
        rule = rule_result.scalar_one_or_none()
        severity = rule.severity if rule else AlertSeverity.WARNING

    alerts = []
    current = period_start
    for i in range(count):
        alert = Alert(
            tenant_id=tenant_id,
            rule_id=rule_id,
            server_id=None,
            target_entity_id=None,
            severity=severity,
            status=AlertStatus.RESOLVED if resolved else AlertStatus.OPEN,
            message=f"CPU usage > 80% (alert {i+1})",
            triggered_at=current,
            resolved_at=current + timedelta(minutes=5) if resolved else None,
            value_at_trigger=85.0 + i,
        )
        db_session.add(alert)
        alerts.append(alert)
        current += timedelta(minutes=interval_minutes)
        if current > period_end:
            break
    await db_session.commit()
    return alerts


# ──────────────────────────────────────────────
# Tests GENERATE_AVAILABILITY
# ──────────────────────────────────────────────

class TestGenerateAvailability:
    """Tests para generate_availability."""

    @pytest.mark.asyncio
    async def test_availability_full_uptime(
        self, db_session: AsyncSession
    ) -> None:
        """Server con métricas continuas → 100% uptime."""
        tenant_id, server_id = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now

        await _create_metrics(db_session, tenant_id, server_id, period_start, period_end, interval_seconds=60)

        payload = await generate_availability(
            db_session, tenant_id, period_start, period_end, {}
        )

        assert payload["summary"]["total_servers"] == 1
        assert payload["summary"]["overall_uptime_pct"] == 100.0
        server = payload["servers"][0]
        assert server["uptime_pct"] == 100.0
        assert server["downtime_seconds"] == 0
        assert server["downtime_windows"] == []

    @pytest.mark.asyncio
    async def test_availability_with_downtime_gap(
        self, db_session: AsyncSession
    ) -> None:
        """Gap en métricas > 5 min → downtime detectado."""
        tenant_id, server_id = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now

        # Gap de 10 minutos en el medio
        gap_at = now - timedelta(minutes=30)
        await _create_metrics(
            db_session, tenant_id, server_id, period_start, period_end,
            gap_at=gap_at, gap_duration=timedelta(minutes=10)
        )

        payload = await generate_availability(
            db_session, tenant_id, period_start, period_end, {}
        )

        server = payload["servers"][0]
        assert server["uptime_pct"] < 100.0
        assert server["downtime_seconds"] > 0
        assert len(server["downtime_windows"]) >= 1
        assert server["downtime_windows"][0]["duration_s"] >= 500  # ~10 min

    @pytest.mark.asyncio
    async def test_availability_no_metrics_zero_uptime(
        self, db_session: AsyncSession
    ) -> None:
        """Server sin métricas → 0% uptime."""
        tenant_id, server_id = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now
        # NO crear métricas

        payload = await generate_availability(
            db_session, tenant_id, period_start, period_end, {}
        )

        server = payload["servers"][0]
        assert server["uptime_pct"] == 0.0
        assert server["downtime_seconds"] == int((period_end - period_start).total_seconds())

    @pytest.mark.asyncio
    async def test_availability_filter_by_server_id(
        self, db_session: AsyncSession
    ) -> None:
        """Filtrar por server_id específico."""
        tenant_id, server_id = await _setup_tenant_with_server(db_session)
        # Crear segundo server
        server2 = Server(
            tenant_id=tenant_id,
            hostname=f"server-{uuid4().hex[:8]}",
            ip="10.0.0.2",
            os="linux",
            status=ServerStatus.ONLINE,
        )
        db_session.add(server2)
        await db_session.commit()

        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now

        await _create_metrics(db_session, tenant_id, server_id, period_start, period_end)
        await _create_metrics(db_session, tenant_id, server2.id, period_start, period_end)

        # Filtrar solo server1
        payload = await generate_availability(
            db_session, tenant_id, period_start, period_end, {"server_id": str(server_id)}
        )

        assert payload["summary"]["total_servers"] == 1
        assert payload["servers"][0]["server_id"] == str(server_id)


# ──────────────────────────────────────────────
# Tests GENERATE_INCIDENTS
# ──────────────────────────────────────────────

class TestGenerateIncidents:
    """Tests para generate_incidents."""

    @pytest.mark.asyncio
    async def test_incidents_groups_by_rule_and_gap(
        self, db_session: AsyncSession
    ) -> None:
        """Alertas de misma regla con gap < 5min = mismo incidente."""
        tenant_id, _ = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now

        rule = await _create_alert_rule(db_session, tenant_id)

        # 3 alertas espaciadas 2 min → mismo incidente
        await _create_alerts_sequence(
            db_session, tenant_id, rule.id, period_start, period_end,
            count=3, interval_minutes=2, resolved=True
        )

        payload = await generate_incidents(
            db_session, tenant_id, period_start, period_end, {}
        )

        assert payload["summary"]["total_incidents"] == 1
        incident = payload["incidents"][0]
        assert incident["alert_count"] == 3
        assert incident["rule_id"] == str(rule.id)
        assert incident["resolved_at"] is not None

    @pytest.mark.asyncio
    async def test_incidents_separate_episodes_by_gap(
        self, db_session: AsyncSession
    ) -> None:
        """Gap > 5min entre alertas de misma regla = incidentes separados."""
        tenant_id, _ = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now

        rule = await _create_alert_rule(db_session, tenant_id)

        # Primer grupo: 2 alertas a 2 min
        await _create_alerts_sequence(
            db_session, tenant_id, rule.id, period_start, period_end,
            count=2, interval_minutes=2, resolved=True
        )

        # Segundo grupo: 2 alertas 10 min después
        second_start = period_start + timedelta(minutes=20)
        await _create_alerts_sequence(
            db_session, tenant_id, rule.id, second_start, period_end,
            count=2, interval_minutes=2, resolved=True
        )

        payload = await generate_incidents(
            db_session, tenant_id, period_start, period_end, {}
        )

        assert payload["summary"]["total_incidents"] == 2
        # Cada incidente tiene 2 alertas
        assert all(i["alert_count"] == 2 for i in payload["incidents"])

    @pytest.mark.asyncio
    async def test_incidents_filters_by_severity(
        self, db_session: AsyncSession
    ) -> None:
        """Filtrar incidentes por severidad."""
        tenant_id, _ = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now

        rule_warning = await _create_alert_rule(db_session, tenant_id, severity=AlertSeverity.WARNING)
        rule_critical = await _create_alert_rule(db_session, tenant_id, severity=AlertSeverity.CRITICAL)

        await _create_alerts_sequence(db_session, tenant_id, rule_warning.id, period_start, period_end, count=2, interval_minutes=2)
        await _create_alerts_sequence(db_session, tenant_id, rule_critical.id, period_start, period_end, count=3, interval_minutes=2)

        # Solo critical
        payload = await generate_incidents(
            db_session, tenant_id, period_start, period_end, {"severity": "critical"}
        )

        assert payload["summary"]["total_incidents"] == 1
        assert payload["summary"]["by_severity"]["critical"] == 1


# ──────────────────────────────────────────────
# Tests GENERATE_ALERTS
# ──────────────────────────────────────────────

class TestGenerateAlerts:
    """Tests para generate_alerts."""

    @pytest.mark.asyncio
    async def test_alerts_catalog_summary_and_list(
        self, db_session: AsyncSession
    ) -> None:
        """Catálogo plano con resumen y lista."""
        tenant_id, _ = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now

        rule1 = await _create_alert_rule(db_session, tenant_id, severity=AlertSeverity.WARNING)
        rule2 = await _create_alert_rule(db_session, tenant_id, severity=AlertSeverity.CRITICAL)

        await _create_alerts_sequence(db_session, tenant_id, rule1.id, period_start, period_end, count=2, resolved=True)
        await _create_alerts_sequence(db_session, tenant_id, rule2.id, period_start, period_end, count=3, resolved=False)

        payload = await generate_alerts(
            db_session, tenant_id, period_start, period_end, {}
        )

        assert payload["summary"]["total"] == 5
        assert payload["summary"]["resolved"] == 2
        assert payload["summary"]["open"] == 3
        assert payload["summary"]["by_severity"]["warning"] == 2
        assert payload["summary"]["by_severity"]["critical"] == 3
        assert len(payload["alerts"]) == 5

    @pytest.mark.asyncio
    async def test_alerts_filter_by_status(
        self, db_session: AsyncSession
    ) -> None:
        """Filtrar alertas por status."""
        tenant_id, _ = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now

        rule = await _create_alert_rule(db_session, tenant_id)
        await _create_alerts_sequence(db_session, tenant_id, rule.id, period_start, period_end, count=3, resolved=True)
        await _create_alerts_sequence(db_session, tenant_id, rule.id, period_start, period_end, count=2, resolved=False)

        payload = await generate_alerts(
            db_session, tenant_id, period_start, period_end, {"status": "resolved"}
        )

        assert payload["summary"]["total"] == 3
        assert all(a["status"] == "resolved" for a in payload["alerts"])

    @pytest.mark.asyncio
    async def test_alerts_filter_by_rule_id(
        self, db_session: AsyncSession
    ) -> None:
        """Filtrar alertas por rule_id."""
        tenant_id, _ = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now

        rule1 = await _create_alert_rule(db_session, tenant_id)
        rule2 = await _create_alert_rule(db_session, tenant_id)

        await _create_alerts_sequence(db_session, tenant_id, rule1.id, period_start, period_end, count=2)
        await _create_alerts_sequence(db_session, tenant_id, rule2.id, period_start, period_end, count=3)

        payload = await generate_alerts(
            db_session, tenant_id, period_start, period_end, {"rule_id": str(rule1.id)}
        )

        assert payload["summary"]["total"] == 2
        assert all(a["rule_id"] == str(rule1.id) for a in payload["alerts"])


# ──────────────────────────────────────────────
# Tests GENERATE_SLA
# ──────────────────────────────────────────────

class TestGenerateSLA:
    """Tests para generate_sla."""

    @pytest.mark.asyncio
    async def test_sla_no_breach_when_uptime_above_target(
        self, db_session: AsyncSession
    ) -> None:
        """Uptime > target → sin breach."""
        tenant_id, server_id = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now

        await _create_metrics(db_session, tenant_id, server_id, period_start, period_end)

        # Target 99.0% (fácil de cumplir)
        payload = await generate_sla(
            db_session, tenant_id, period_start, period_end, {"target_pct": 99.0}
        )

        assert payload["breach"] is False
        assert payload["target_pct"] == 99.0
        assert payload["achieved_pct"] > 99.0
        assert payload["credit_due_pct"] == 0
        assert len(payload["servers"]) == 1
        assert payload["servers"][0]["breach"] is False

    @pytest.mark.asyncio
    async def test_sla_breach_when_uptime_below_target(
        self, db_session: AsyncSession
    ) -> None:
        """Uptime < target → breach + credit."""
        tenant_id, server_id = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now

        # Gap grande → uptime bajo
        gap_at = now - timedelta(minutes=30)
        await _create_metrics(
            db_session, tenant_id, server_id, period_start, period_end,
            gap_at=gap_at, gap_duration=timedelta(minutes=30)
        )

        payload = await generate_sla(
            db_session, tenant_id, period_start, period_end, {"target_pct": 99.9}
        )

        assert payload["breach"] is True
        assert payload["achieved_pct"] < 99.9
        assert payload["credit_due_pct"] > 0
        assert payload["servers"][0]["breach"] is True

    @pytest.mark.asyncio
    async def test_sla_uses_tenant_settings_default_target(
        self, db_session: AsyncSession
    ) -> None:
        """Si no pasa target_pct, usa tenant.settings.sla.default_target_pct."""
        tenant_id, server_id = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now

        await _create_metrics(db_session, tenant_id, server_id, period_start, period_end)

        # No pasar target_pct → debe usar 99.9 de settings
        payload = await generate_sla(
            db_session, tenant_id, period_start, period_end, {}
        )

        assert payload["target_pct"] == 99.9


# ──────────────────────────────────────────────
# Tests GENERATE_METRICS
# ──────────────────────────────────────────────

class TestGenerateMetrics:
    """Tests para generate_metrics."""

    @pytest.mark.asyncio
    async def test_metrics_returns_rollup_points(
        self, db_session: AsyncSession
    ) -> None:
        """Query rollups existentes → devuelve points."""
        tenant_id, server_id = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now

        # Crear rollups de 5m directamente (simula worker)
        for i in range(12):  # 12 buckets de 5m = 1 hora
            bucket = period_start + timedelta(minutes=5 * i)
            rollup = MetricRollup(
                period=RollupPeriod.MIN_5,
                bucket_start=bucket,
                tenant_id=tenant_id,
                server_id=server_id,
                type=MetricType.CPU_USAGE,
                count=5,
                avg=45.0 + i,
                min=40.0 + i,
                max=50.0 + i,
                last=46.0 + i,
            )
            db_session.add(rollup)
        await db_session.commit()

        payload = await generate_metrics(
            db_session, tenant_id, period_start, period_end,
            {"server_id": str(server_id), "type": "cpu_usage", "period": "5m"}
        )

        assert payload["server_id"] == str(server_id)
        assert payload["type"] == "cpu_usage"
        assert payload["period"] == "5m"
        assert len(payload["points"]) == 12
        assert payload["points"][0]["avg"] == 45.0
        assert payload["points"][-1]["avg"] == 56.0

    @pytest.mark.asyncio
    async def test_metrics_downsampling_when_exceeds_max_points(
        self, db_session: AsyncSession
    ) -> None:
        """Más puntos que max_points → downsampling."""
        tenant_id, server_id = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now

        # 100 rollups (más que max_points=50 default)
        for i in range(100):
            bucket = period_start + timedelta(minutes=1 * i)  # 1m buckets
            rollup = MetricRollup(
                period=RollupPeriod.MIN_1,
                bucket_start=bucket,
                tenant_id=tenant_id,
                server_id=server_id,
                type=MetricType.CPU_USAGE,
                count=1,
                avg=float(i),
                min=float(i),
                max=float(i),
                last=float(i),
            )
            db_session.add(rollup)
        await db_session.commit()

        payload = await generate_metrics(
            db_session, tenant_id, period_start, period_end,
            {"server_id": str(server_id), "type": "cpu_usage", "period": "1m", "max_points": 50}
        )

        assert len(payload["points"]) <= 50
        # Debe haber hecho step ~2
        assert payload["points"][0]["avg"] == 0.0


# ──────────────────────────────────────────────
# Tests DISPATCHER (generate_report)
# ──────────────────────────────────────────────

class TestGenerateReportDispatcher:
    """Tests para el dispatcher generate_report."""

    @pytest.mark.asyncio
    async def test_dispatch_all_types(
        self, db_session: AsyncSession
    ) -> None:
        """generate_report despacha a cada generador."""
        tenant_id, server_id = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)
        period_start = now - timedelta(hours=1)
        period_end = now

        await _create_metrics(db_session, tenant_id, server_id, period_start, period_end)

        for rtype in ["availability", "incidents", "alerts", "sla", "metrics"]:
            if rtype == "metrics":
                payload = await generate_report(
                    db_session, tenant_id, rtype, period_start, period_end,
                    {"server_id": str(server_id), "type": "cpu_usage", "period": "5m"}
                )
            else:
                payload = await generate_report(
                    db_session, tenant_id, rtype, period_start, period_end, {}
                )
            assert isinstance(payload, dict)
            assert "summary" in payload or "points" in payload or "target_pct" in payload

    @pytest.mark.asyncio
    async def test_dispatch_unknown_type_raises(
        self, db_session: AsyncSession
    ) -> None:
        """Tipo desconocido → ValueError."""
        tenant_id, _ = await _setup_tenant_with_server(db_session)
        now = datetime.now(UTC)

        with pytest.raises(ValueError, match="Unknown report type"):
            await generate_report(
                db_session, tenant_id, "not_a_type", now, now, {}
            )
