"""Integration tests for Alert Delivery Runner (T4).

Covers: pending→sent, pending→failed (DeliveryError), config_missing,
unknown_channel, and recovery (failed not re-selected).
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.models.alert import (
    Alert,
    AlertDelivery,
    AlertOperator,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    EntityType,
)
from app.models.server import Server, ServerStatus
from app.models.tenant import Tenant
from app.workers.delivery import DeliveryChannel, DeliveryError
from app.workers.delivery import get_channel as get_channel_real
from app.workers.delivery_runner import DeliveryRunSummary, deliver_alerts
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

async def _seed_tenant_server_rule_alert_delivery(
    session: AsyncSession,
    *,
    channel: str = "webhook",
    channel_config: dict | None = None,
) -> tuple[Tenant, Server, AlertRule, Alert, AlertDelivery]:
    """Create minimal tenant, server, rule, alert, and pending delivery."""
    tenant = Tenant(name="test-tenant", slug=f"test-{uuid4().hex[:8]}")
    session.add(tenant)
    await session.flush()

    server = Server(
        tenant_id=tenant.id,
        hostname="test-server",
        ip="10.0.0.1",
        os="linux",
        status=ServerStatus.ONLINE,
    )
    session.add(server)
    await session.flush()

    rule_channels = {}
    if channel_config is not None:
        rule_channels[channel] = channel_config

    rule = AlertRule(
        tenant_id=tenant.id,
        entity_type=EntityType.SERVER,
        entity_id=server.id,
        metric="cpu_usage",
        operator=AlertOperator.GT,
        threshold=80.0,
        duration_s=60,
        severity=AlertSeverity.WARNING,
        channels=rule_channels,
        is_active=True,
    )
    session.add(rule)
    await session.flush()

    alert = Alert(
        rule_id=rule.id,
        server_id=server.id,
        tenant_id=tenant.id,
        severity=AlertSeverity.WARNING,
        status=AlertStatus.OPEN,
        message="cpu_usage > 80 sustained >= 60s",
        triggered_at=datetime.now(UTC),
        value_at_trigger=85.0,
    )
    session.add(alert)
    await session.flush()

    delivery = AlertDelivery(
        alert_id=alert.id,
        channel=channel,
        status="pending",
        tenant_id=tenant.id,
    )
    session.add(delivery)
    await session.flush()

    return tenant, server, rule, alert, delivery


# ──────────────────────────────────────────────
# Stub Channel for Testing
# ──────────────────────────────────────────────

class StubChannel:
    """Stub channel that returns a fixed ref or raises DeliveryError."""

    name = "stub"

    def __init__(
        self,
        return_ref: str = "ref-123",
        raise_error: DeliveryError | None = None,
    ) -> None:
        self.return_ref = return_ref
        self.raise_error = raise_error
        self.calls: list[dict] = []

    async def send(self, *, alert: Alert, rule: AlertRule, server: Server | None, channel_config: dict) -> str:
        self.calls.append({
            "alert_id": alert.id,
            "rule_id": rule.id,
            "server_id": server.id if server else None,
            "channel_config": channel_config,
        })
        if self.raise_error:
            raise self.raise_error
        return self.return_ref


# ──────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────

class TestDeliveryRunner:
    """Tests for deliver_alerts() runner."""

    @pytest.mark.asyncio
    async def test_pending_to_sent_webhook_mock(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """pending delivery with webhook → sent with external_ref, delivered_at, error=None."""
        _, _, _, _, delivery = await _seed_tenant_server_rule_alert_delivery(
            db_session,
            channel="webhook",
            channel_config={"url": "http://example.invalid/hook"},
        )

        stub = StubChannel(return_ref="ref-123")
        monkeypatch.setattr("app.workers.delivery_runner.get_channel", lambda name: stub)

        summary = await deliver_alerts(db_session)

        assert isinstance(summary, DeliveryRunSummary)
        assert summary.sent == 1
        assert summary.failed == 0
        assert summary.total == 1

        await db_session.refresh(delivery)
        assert delivery.status == "sent"
        assert delivery.external_ref == "ref-123"
        assert delivery.delivered_at is not None
        assert delivery.error is None

    @pytest.mark.asyncio
    async def test_delivery_error_becomes_failed(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DeliveryError raised by channel → failed with error containing reason."""
        _, _, _, _, delivery = await _seed_tenant_server_rule_alert_delivery(
            db_session,
            channel="webhook",
            channel_config={"url": "http://example.invalid/hook"},
        )

        stub = StubChannel(raise_error=DeliveryError("boom", "http_error"))
        monkeypatch.setattr("app.workers.delivery_runner.get_channel", lambda name: stub)

        summary = await deliver_alerts(db_session)

        assert summary.sent == 0
        assert summary.failed == 1

        await db_session.refresh(delivery)
        assert delivery.status == "failed"
        assert delivery.error is not None
        assert "http_error" in delivery.error
        assert "boom" in delivery.error
        assert delivery.external_ref is None
        assert delivery.delivered_at is None

    @pytest.mark.asyncio
    async def test_config_missing_channel_not_in_rule(
        self, db_session: AsyncSession
    ) -> None:
        """delivery.channel='webhook' but rule.channels={} → failed with config_missing."""
        _, _, _, _, delivery = await _seed_tenant_server_rule_alert_delivery(
            db_session,
            channel="webhook",
            channel_config=None,  # rule.channels will be {}
        )

        # No monkeypatch needed — get_channel will be called but config_missing triggers first
        summary = await deliver_alerts(db_session)

        assert summary.sent == 0
        assert summary.failed == 1

        await db_session.refresh(delivery)
        assert delivery.status == "failed"
        assert delivery.error is not None
        assert "config_missing" in delivery.error
        assert delivery.external_ref is None
        assert delivery.delivered_at is None

    @pytest.mark.asyncio
    async def test_unknown_channel_failed(
        self, db_session: AsyncSession
    ) -> None:
        """delivery.channel='telegram' (unknown) → failed with unknown_channel."""
        tenant, server, rule, alert, _ = await _seed_tenant_server_rule_alert_delivery(
            db_session,
            channel="webhook",
            channel_config={"url": "http://example.invalid/hook"},
        )

        # Remove the webhook delivery that was created by the helper
        pending_deliveries = (
            await db_session.scalars(
                select(AlertDelivery).where(AlertDelivery.status == "pending")
            )
        ).all()
        for d in pending_deliveries:
            await db_session.delete(d)
        await db_session.flush()

        # Add telegram to rule.channels so config_missing does not trigger first
        rule.channels = {
            "webhook": {"url": "http://example.invalid/hook"},
            "telegram": {},  # dummy config so get_channel is called
        }
        db_session.add(rule)
        await db_session.flush()

        # Insert delivery with unknown channel directly (bypassing schema validation)
        delivery = AlertDelivery(
            alert_id=alert.id,
            channel="telegram",
            status="pending",
            tenant_id=tenant.id,
        )
        db_session.add(delivery)
        await db_session.flush()

        summary = await deliver_alerts(db_session)

        assert summary.sent == 0
        assert summary.failed == 1

        await db_session.refresh(delivery)
        assert delivery.status == "failed"
        assert delivery.error is not None
        assert "unknown_channel" in delivery.error
        assert delivery.external_ref is None
        assert delivery.delivered_at is None

    @pytest.mark.asyncio
    async def test_recovery_failed_not_reselected(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Failed delivery is NOT re-selected on next run (status persisted)."""
        _, _, _, _, delivery = await _seed_tenant_server_rule_alert_delivery(
            db_session,
            channel="webhook",
            channel_config={"url": "http://example.invalid/hook"},
        )

        # First run: fail it
        stub = StubChannel(raise_error=DeliveryError("boom", "http_error"))
        monkeypatch.setattr("app.workers.delivery_runner.get_channel", lambda name: stub)

        summary1 = await deliver_alerts(db_session)
        assert summary1.failed == 1

        await db_session.refresh(delivery)
        assert delivery.status == "failed"

        # Second run: should NOT process it again (no longer pending)
        stub2 = StubChannel(return_ref="ref-456")
        monkeypatch.setattr("app.workers.delivery_runner.get_channel", lambda name: stub2)

        summary2 = await deliver_alerts(db_session)
        assert summary2.sent == 0
        assert summary2.failed == 0
        assert summary2.total == 0

        # Verify delivery unchanged
        await db_session.refresh(delivery)
        assert delivery.status == "failed"
        assert delivery.error is not None
        assert "http_error" in delivery.error

    @pytest.mark.asyncio
    async def test_multiple_deliveries_mixed_results(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multiple pending deliveries: some sent, some failed."""
        tenant, server, rule, alert, delivery1 = await _seed_tenant_server_rule_alert_delivery(
            db_session,
            channel="webhook",
            channel_config={"url": "http://example.invalid/hook1"},
        )

        # Second delivery for same alert, different channel
        delivery2 = AlertDelivery(
            alert_id=alert.id,
            channel="email",
            status="pending",
            tenant_id=tenant.id,
        )
        db_session.add(delivery2)
        await db_session.flush()

        # Update rule with email config
        rule.channels = {
            "webhook": {"url": "http://example.invalid/hook1"},
            "email": {"to": ["ops@example.com"]},
        }
        db_session.add(rule)
        await db_session.flush()

        # Stub for webhook (succeeds), email will fail due to SMTP not configured
        webhook_stub = StubChannel(return_ref="webhook-ref-123")
        email_stub = StubChannel(raise_error=DeliveryError("SMTP not configured", "config_missing"))

        def get_channel_mock(name: str) -> "DeliveryChannel":
            if name == "webhook":
                return webhook_stub
            if name == "email":
                return email_stub
            return get_channel_real(name)  # fallback to real for unknown

        monkeypatch.setattr("app.workers.delivery_runner.get_channel", get_channel_mock)

        summary = await deliver_alerts(db_session)

        assert summary.sent == 1
        assert summary.failed == 1

        await db_session.refresh(delivery1)
        await db_session.refresh(delivery2)

        assert delivery1.status == "sent"
        assert delivery1.external_ref == "webhook-ref-123"
        assert delivery1.error is None

        assert delivery2.status == "failed"
        assert delivery2.error is not None
        assert "config_missing" in delivery2.error
