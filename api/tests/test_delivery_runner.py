"""Integration tests for Alert Delivery Runner (T4).

Covers: pending→sent, pending→failed (DeliveryError), config_missing,
unknown_channel, recovery (failed not re-selected), and config snapshot
fallback for job-failure alerts (rule_id=None).
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.models.alert import (
    Alert,
    AlertDelivery,
    AlertOperator,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    EntityType,
)
from app.models.job import Job, JobKind, JobStatus
from app.models.server import Server, ServerStatus
from app.models.tenant import Tenant
from app.workers.delivery import DeliveryChannel, DeliveryError
from app.workers.delivery import get_channel as get_channel_real
from app.workers.delivery.email import EmailChannel
from app.workers.delivery.webhook import WebhookChannel
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


async def _seed_job_failure_alert_delivery(
    session: AsyncSession,
    *,
    channel: str = "webhook",
    channel_config: dict | None = None,
    config_snapshot: dict | None = None,
) -> tuple[Tenant, Server, Job, Alert, AlertDelivery]:
    """Create tenant, server, job, job-failure alert (rule_id=None), and pending delivery.

    The delivery can carry a config_snapshot (the new config column) independently
    of what the job.config.channels has. This tests the snapshot fallback logic.
    """
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

    job_channels = {}
    if channel_config is not None:
        job_channels[channel] = channel_config

    job = Job(
        tenant_id=tenant.id,
        server_id=server.id,
        name="test-job",
        command="exit 1",
        schedule_cron="* * * * *",
        kind=JobKind.CRON,
        status=JobStatus.ACTIVE,
        config={"channels": job_channels} if job_channels else {},
        timeout_s=30,
    )
    session.add(job)
    await session.flush()

    # Create job-failure alert directly (rule_id=None)
    alert = Alert(
        rule_id=None,  # Job failure alerts have no rule
        server_id=server.id,
        tenant_id=tenant.id,
        severity=AlertSeverity.CRITICAL,
        status=AlertStatus.OPEN,
        message=f"Job '{job.name}' failed (exit=1)",
        triggered_at=datetime.now(UTC),
        value_at_trigger=1.0,
    )
    session.add(alert)
    await session.flush()

    delivery = AlertDelivery(
        alert_id=alert.id,
        channel=channel,
        status="pending",
        tenant_id=tenant.id,
        config=config_snapshot,
    )
    session.add(delivery)
    await session.flush()

    return tenant, server, job, alert, delivery


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

    async def send(self, *, alert: Alert, rule: AlertRule | None, server: Server | None, channel_config: dict) -> str:
        self.calls.append({
            "alert_id": alert.id,
            "rule_id": rule.id if rule else None,
            "server_id": server.id if server else None,
            "channel_config": channel_config,
        })
        if self.raise_error:
            raise self.raise_error
        return self.return_ref


# ──────────────────────────────────────────────
# Real Channel Capture for Payload Assertions
# ──────────────────────────────────────────────

class CaptureWebhookChannel:
    """Capture webhook payload for assertion without sending HTTP."""

    name = "webhook"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send(self, *, alert: Alert, rule: AlertRule | None, server: Server | None, channel_config: dict) -> str:
        channel = WebhookChannel()
        payload = channel._build_payload(alert, rule, server)
        self.calls.append({
            "alert_id": alert.id,
            "rule_id": rule.id if rule else None,
            "server_id": server.id if server else None,
            "channel_config": channel_config,
            "payload": payload,
        })
        return f"captured:{alert.id}"


class CaptureEmailChannel:
    """Capture email message for assertion without sending SMTP."""

    name = "email"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send(self, *, alert: Alert, rule: AlertRule | None, server: Server | None, channel_config: dict) -> str:
        channel = EmailChannel()
        settings = get_settings()
        to_emails = channel_config.get("to", ["test@example.com"])
        message = channel._build_message(alert, rule, server, to_emails, settings)
        self.calls.append({
            "alert_id": alert.id,
            "rule_id": rule.id if rule else None,
            "server_id": server.id if server else None,
            "channel_config": channel_config,
            "subject": message["Subject"],
            "body": message.get_content(),
        })
        return f"captured:{alert.id}"


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

    @pytest.mark.asyncio
    async def test_job_failure_alert_with_config_snapshot_sent(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Job-failure alert (rule_id=None) with delivery.config snapshot → sent.

        This is the core regression test: before the fix, deliver_alerts would
        raise AttributeError on rule.channels because rule is None. With the
        snapshot on delivery.config, it should succeed.
        """
        _, _, _, _, delivery = await _seed_job_failure_alert_delivery(
            db_session,
            channel="webhook",
            channel_config=None,  # job.config.channels empty
            config_snapshot={"url": "http://example.invalid/hook"},  # but delivery has snapshot
        )

        stub = StubChannel(return_ref="job-fail-ref-123")
        monkeypatch.setattr("app.workers.delivery_runner.get_channel", lambda name: stub)

        summary = await deliver_alerts(db_session)

        assert summary.sent == 1
        assert summary.failed == 0

        await db_session.refresh(delivery)
        assert delivery.status == "sent"
        assert delivery.external_ref == "job-fail-ref-123"
        assert delivery.delivered_at is not None
        assert delivery.error is None
        # Verify the stub received the snapshot config
        assert stub.calls[0]["channel_config"] == {"url": "http://example.invalid/hook"}
        # rule_id should be None for job-failure alerts
        assert stub.calls[0]["rule_id"] is None

    @pytest.mark.asyncio
    async def test_legacy_delivery_without_snapshot_falls_back_to_rule_channels(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rule-based delivery with config=None (legacy row) → resolves from rule.channels → sent.

        Ensures backward compatibility: rows created before the migration have
        config=NULL and should fall back to rule.channels.
        """
        _, _, _, _, delivery = await _seed_tenant_server_rule_alert_delivery(
            db_session,
            channel="webhook",
            channel_config={"url": "http://example.invalid/hook"},
        )

        # Simulate legacy row: delivery.config = None (predates migration)
        delivery.config = None
        db_session.add(delivery)
        await db_session.flush()

        stub = StubChannel(return_ref="legacy-ref-456")
        monkeypatch.setattr("app.workers.delivery_runner.get_channel", lambda name: stub)

        summary = await deliver_alerts(db_session)

        assert summary.sent == 1
        assert summary.failed == 0

        await db_session.refresh(delivery)
        assert delivery.status == "sent"
        assert delivery.external_ref == "legacy-ref-456"
        # Verify the stub received the rule's channel config
        assert stub.calls[0]["channel_config"] == {"url": "http://example.invalid/hook"}

    @pytest.mark.asyncio
    async def test_delivery_no_snapshot_no_rule_config_missing_not_exception(
        self, db_session: AsyncSession
    ) -> None:
        """Delivery with neither config snapshot nor rule.channels → config_missing (failed, no exception).

        Job-failure alert where job.config.channels had no entry for this channel,
        and delivery.config is None. Should fail gracefully with config_missing
        instead of raising AttributeError.
        """
        _, _, _, _, delivery = await _seed_job_failure_alert_delivery(
            db_session,
            channel="webhook",
            channel_config=None,  # job.config.channels empty
            config_snapshot=None,  # no snapshot on delivery
        )

        # No monkeypatch — we should not even reach get_channel
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
    async def test_batch_isolation_one_fails_others_still_sent(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One failing delivery (config_missing) does not block a subsequent healthy delivery in same batch.

        This verifies the fix for the bug where an exception outside the try block
        would crash the entire runner, preventing all subsequent deliveries.
        """
        tenant, server, rule, alert, delivery1 = await _seed_tenant_server_rule_alert_delivery(
            db_session,
            channel="webhook",
            channel_config=None,  # This will cause config_missing
        )

        # Second delivery for same alert, different channel WITH config
        delivery2 = AlertDelivery(
            alert_id=alert.id,
            channel="email",
            status="pending",
            tenant_id=tenant.id,
            config={"to": ["ops@example.com"]},  # snapshot present
        )
        db_session.add(delivery2)
        await db_session.flush()

        # Only email stub needed (webhook will fail at config_missing before get_channel)
        email_stub = StubChannel(return_ref="email-ref-789")

        def get_channel_mock(name: str) -> "DeliveryChannel":
            if name == "email":
                return email_stub
            return get_channel_real(name)

        monkeypatch.setattr("app.workers.delivery_runner.get_channel", get_channel_mock)

        summary = await deliver_alerts(db_session)

        # First delivery fails (config_missing), second succeeds
        assert summary.sent == 1
        assert summary.failed == 1

        await db_session.refresh(delivery1)
        await db_session.refresh(delivery2)

        assert delivery1.status == "failed"
        assert "config_missing" in delivery1.error

        assert delivery2.status == "sent"
        assert delivery2.external_ref == "email-ref-789"
        assert delivery2.error is None

    @pytest.mark.asyncio
    async def test_batch_isolation_unresolvable_alert_does_not_crash_runner(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A delivery whose alert/rule cannot be resolved fails alone, not the whole batch.

        The alert/rule/server resolution happens before the send try-block. If it
        raises, the runner must mark only that delivery as failed and keep
        processing the remaining ones, preserving the "runner never crashes"
        guarantee for every tenant in the batch.
        """
        tenant, server, rule, alert, seeded_delivery = await _seed_tenant_server_rule_alert_delivery(
            db_session,
            channel="email",
            channel_config={"to": ["ops@example.com"]},
        )

        # A broken delivery: alert_id points to a row that will not exist.
        # The relationship resolves to None, which the runner must treat as an
        # isolated failure instead of crashing the batch.
        orphan_delivery = AlertDelivery(
            alert_id=uuid4(),
            channel="email",
            status="pending",
            tenant_id=tenant.id,
            config={"to": ["ops@example.com"]},
        )
        db_session.add(orphan_delivery)
        await db_session.flush()

        email_stub = StubChannel(return_ref="email-ref-orphan")
        monkeypatch.setattr(
            "app.workers.delivery_runner.get_channel", lambda name: email_stub
        )

        summary = await deliver_alerts(db_session)

        await db_session.refresh(seeded_delivery)
        await db_session.refresh(orphan_delivery)

        # The healthy delivery still went out; the orphan failed alone.
        assert seeded_delivery.status == "sent"
        assert seeded_delivery.external_ref == "email-ref-orphan"
        assert summary.sent == 1
        assert summary.failed == 1
        assert orphan_delivery.status == "failed"
        assert orphan_delivery.error is not None
        assert "unresolved" in orphan_delivery.error
        assert "alert_missing" in orphan_delivery.error


class TestWebhookPayload:
    """Tests for webhook payload structure with optional rule."""

    @pytest.mark.asyncio
    async def test_job_failure_alert_payload_has_source_job_and_null_rule(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Job-failure alert (rule_id=None) → payload has source='job' and rule=null."""
        _, _, _, _, delivery = await _seed_job_failure_alert_delivery(
            db_session,
            channel="webhook",
            channel_config=None,
            config_snapshot={"url": "http://example.invalid/hook"},
        )

        capture = CaptureWebhookChannel()
        monkeypatch.setattr("app.workers.delivery_runner.get_channel", lambda name: capture)

        summary = await deliver_alerts(db_session)

        assert summary.sent == 1
        assert len(capture.calls) == 1

        payload = capture.calls[0]["payload"]
        assert payload["source"] == "job"
        assert payload["rule"] is None
        assert payload["alert"]["id"] == str(delivery.alert_id)
        assert payload["alert"]["severity"] == "critical"
        assert payload["server"] is not None

        await db_session.refresh(delivery)
        assert delivery.status == "sent"

    @pytest.mark.asyncio
    async def test_rule_based_alert_payload_has_source_rule_and_full_rule_block(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rule-based alert → payload has source='rule' and full rule block with all six fields."""
        _, _, rule, _, delivery = await _seed_tenant_server_rule_alert_delivery(
            db_session,
            channel="webhook",
            channel_config={"url": "http://example.invalid/hook"},
        )

        capture = CaptureWebhookChannel()
        monkeypatch.setattr("app.workers.delivery_runner.get_channel", lambda name: capture)

        summary = await deliver_alerts(db_session)

        assert summary.sent == 1
        assert len(capture.calls) == 1

        payload = capture.calls[0]["payload"]
        assert payload["source"] == "rule"
        assert payload["rule"] is not None
        rule_block = payload["rule"]
        assert rule_block["id"] == str(rule.id)
        assert rule_block["metric"] == rule.metric
        assert rule_block["operator"] == rule.operator.value
        assert rule_block["threshold"] == rule.threshold
        assert rule_block["duration_s"] == rule.duration_s
        assert rule_block["severity"] == rule.severity.value
        assert payload["alert"]["id"] == str(delivery.alert_id)
        assert payload["server"] is not None

        await db_session.refresh(delivery)
        assert delivery.status == "sent"


class TestEmailRendering:
    """Tests for email rendering with optional rule."""

    @pytest.mark.asyncio
    async def test_job_failure_alert_email_omits_rule_block(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Job-failure alert (rule_id=None) → email subject uses 'Job Failure', body omits Rule block."""
        _, _, _, _, delivery = await _seed_job_failure_alert_delivery(
            db_session,
            channel="email",
            channel_config=None,
            config_snapshot={"to": ["ops@example.com"]},
        )

        capture = CaptureEmailChannel()
        monkeypatch.setattr("app.workers.delivery_runner.get_channel", lambda name: capture)

        summary = await deliver_alerts(db_session)

        assert summary.sent == 1
        assert len(capture.calls) == 1

        call = capture.calls[0]
        subject = call["subject"]
        body = call["body"]

        # Subject should contain "Job Failure" not a metric name
        assert "Job Failure" in subject
        assert "ALERT CRITICAL" in subject

        # Body should NOT contain Rule block
        assert "Rule:" not in body
        assert "ID:" not in body or "Alert ID:" in body  # Alert ID is OK, Rule ID is not
        assert "Metric:" not in body
        assert "Operator:" not in body
        assert "Threshold:" not in body
        assert "Duration:" not in body
        assert "Severity:" not in body or f"Severity: {AlertSeverity.CRITICAL.value}" in body  # Alert severity is OK

        # Body should contain alert info and server info
        assert "Alert ID:" in body
        assert "Message:" in body
        assert "Server:" in body

        await db_session.refresh(delivery)
        assert delivery.status == "sent"

    @pytest.mark.asyncio
    async def test_rule_based_alert_email_includes_rule_block(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rule-based alert → email subject uses rule.metric, body includes Rule block with all fields."""
        _, _, rule, _, delivery = await _seed_tenant_server_rule_alert_delivery(
            db_session,
            channel="email",
            channel_config={"to": ["ops@example.com"]},
        )

        capture = CaptureEmailChannel()
        monkeypatch.setattr("app.workers.delivery_runner.get_channel", lambda name: capture)

        summary = await deliver_alerts(db_session)

        assert summary.sent == 1
        assert len(capture.calls) == 1

        call = capture.calls[0]
        subject = call["subject"]
        body = call["body"]

        # Subject should contain rule.metric
        assert rule.metric in subject
        assert "ALERT WARNING" in subject

        # Body should contain Rule block with all six fields
        assert "Rule:" in body
        assert f"ID: {rule.id}" in body
        assert f"Metric: {rule.metric}" in body
        assert f"Operator: {rule.operator.value}" in body
        assert f"Threshold: {rule.threshold}" in body
        assert f"Duration: {rule.duration_s}s" in body
        assert f"Severity: {rule.severity.value}" in body

        # Body should contain alert info and server info
        assert "Alert ID:" in body
        assert "Server:" in body

        await db_session.refresh(delivery)
        assert delivery.status == "sent"
