"""Unit tests for Email delivery channel (T3)."""

import email as email_lib
import smtplib
from datetime import UTC, datetime
from email.message import Message
from typing import Literal
from uuid import uuid4

import app.workers.delivery.email as email_module
import pytest
from app.core.config import get_settings
from app.models.alert import (
    Alert,
    AlertOperator,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    EntityType,
)
from app.models.server import Server, ServerStatus
from app.models.tenant import Tenant
from app.workers.delivery import DeliveryError, get_channel
from app.workers.delivery.email import EmailChannel

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _make_tenant_server_rule_alert() -> tuple[Tenant, Server, AlertRule, Alert]:
    """Create minimal tenant, server, rule, alert for testing."""
    tenant = Tenant(name="test-tenant", slug=f"test-{uuid4().hex[:8]}")
    server = Server(
        tenant_id=tenant.id,
        hostname="test-server",
        ip="10.0.0.1",
        os="linux",
        status=ServerStatus.ONLINE,
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
        channels={"email": {"to": ["ops@example.com"]}},
        is_active=True,
    )
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
    return tenant, server, rule, alert


# ──────────────────────────────────────────────
# SMTP Stub for testing
# ──────────────────────────────────────────────

class MockSMTP:
    """Mock SMTP class that records calls instead of connecting."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.starttls_called = False
        self.login_called = False
        self.login_args: tuple[str, str] | None = None
        self.send_message_called = False
        self.sent_message: str | None = None
        self.should_raise: Exception | None = None

    def __enter__(self) -> "MockSMTP":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> Literal[False]:
        return False

    def starttls(self) -> None:
        self.starttls_called = True

    def login(self, user: str, password: str) -> None:
        self.login_called = True
        self.login_args = (user, password)

    def send_message(self, msg: Message) -> None:
        self.send_message_called = True
        self.sent_message = msg.as_string()
        if self.should_raise:
            raise self.should_raise


# ──────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────

class TestEmailChannel:
    """Tests for EmailChannel.send()."""

    @pytest.mark.asyncio
    async def test_send_smtp_disabled_raises_config_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When SMTP is not configured (smtp_enabled=False), raises DeliveryError config_missing."""
        monkeypatch.setenv("SMTP_HOST", "")
        monkeypatch.setenv("SMTP_FROM", "")
        get_settings.cache_clear()

        channel = EmailChannel()
        _, server, rule, alert = _make_tenant_server_rule_alert()
        channel_config = {"to": ["ops@example.com"]}

        with pytest.raises(DeliveryError) as exc:
            await channel.send(alert=alert, rule=rule, server=server, channel_config=channel_config)

        assert exc.value.reason == "config_missing"
        assert "SMTP not configured" in exc.value.message

    @pytest.mark.asyncio
    async def test_send_missing_to_raises_config_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing 'to' in channel_config raises DeliveryError config_missing."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_FROM", "alerts@example.com")
        get_settings.cache_clear()

        channel = EmailChannel()
        _, server, rule, alert = _make_tenant_server_rule_alert()
        channel_config: dict = {}  # missing 'to'

        with pytest.raises(DeliveryError) as exc:
            await channel.send(alert=alert, rule=rule, server=server, channel_config=channel_config)

        assert exc.value.reason == "config_missing"
        assert "to" in exc.value.message.lower()

    @pytest.mark.asyncio
    async def test_send_empty_to_raises_config_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty 'to' list in channel_config raises DeliveryError config_missing."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_FROM", "alerts@example.com")
        get_settings.cache_clear()

        channel = EmailChannel()
        _, server, rule, alert = _make_tenant_server_rule_alert()
        channel_config: dict[str, list[str]] = {"to": []}

        with pytest.raises(DeliveryError) as exc:
            await channel.send(alert=alert, rule=rule, server=server, channel_config=channel_config)

        assert exc.value.reason == "config_missing"
        assert "to" in exc.value.message.lower()

    @pytest.mark.asyncio
    async def test_send_happy_path_with_smtp_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Happy path: SMTP stub records calls, message has correct headers/body, returns email:ref."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_PORT", "587")
        monkeypatch.setenv("SMTP_USER", "smtpuser")
        monkeypatch.setenv("SMTP_PASSWORD", "smtppass")
        monkeypatch.setenv("SMTP_FROM", "alerts@example.com")
        monkeypatch.setenv("SMTP_STARTTLS", "true")
        get_settings.cache_clear()

        mock_smtp = MockSMTP("smtp.example.com", 587)

        def smtp_factory(host: str, port: int) -> MockSMTP:
            return mock_smtp

        monkeypatch.setattr(email_module.smtplib, "SMTP", smtp_factory)

        channel = EmailChannel()
        _, server, rule, alert = _make_tenant_server_rule_alert()
        channel_config = {"to": ["ops@example.com", "dev@example.com"]}

        ref = await channel.send(alert=alert, rule=rule, server=server, channel_config=channel_config)

        # Assert stub was called
        assert mock_smtp.starttls_called is True
        assert mock_smtp.login_called is True
        assert mock_smtp.login_args == ("smtpuser", "smtppass")
        assert mock_smtp.send_message_called is True

        # Assert returned ref
        assert ref == "email:ops@example.com,dev@example.com"

        # Assert message content - parse email properly to handle encoding
        sent_msg = mock_smtp.sent_message
        assert sent_msg is not None
        parsed = email_lib.message_from_string(sent_msg)
        assert parsed["From"] == "alerts@example.com"
        assert parsed["To"] == "ops@example.com, dev@example.com"
        assert parsed["Subject"] == "[SPSAAS] ALERT WARNING cpu_usage on test-server"

        # Get decoded body using legacy API
        body = parsed.get_payload(decode=True)
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        assert f"Alert ID: {alert.id}" in body
        assert "Severity: warning" in body
        assert "cpu_usage > 80 sustained >= 60s" in body
        assert "Value at Trigger: 85.0" in body
        assert "Rule:" in body
        assert "Metric: cpu_usage" in body
        assert "Operator: gt" in body
        assert "Threshold: 80.0" in body
        assert "Duration: 60s" in body
        assert "Hostname: test-server" in body
        assert "IP: 10.0.0.1" in body
        assert "OS: linux" in body

    @pytest.mark.asyncio
    async def test_send_starttls_disabled_no_user(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """STARTTLS disabled and no user: starttls and login NOT called, send_message called."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_PORT", "25")
        monkeypatch.setenv("SMTP_USER", "")
        monkeypatch.setenv("SMTP_PASSWORD", "")
        monkeypatch.setenv("SMTP_FROM", "alerts@example.com")
        monkeypatch.setenv("SMTP_STARTTLS", "false")
        get_settings.cache_clear()

        mock_smtp = MockSMTP("smtp.example.com", 25)

        def smtp_factory(host: str, port: int) -> MockSMTP:
            return mock_smtp

        monkeypatch.setattr(email_module.smtplib, "SMTP", smtp_factory)

        channel = EmailChannel()
        _, server, rule, alert = _make_tenant_server_rule_alert()
        channel_config = {"to": ["ops@example.com"]}

        ref = await channel.send(alert=alert, rule=rule, server=server, channel_config=channel_config)

        assert mock_smtp.starttls_called is False
        assert mock_smtp.login_called is False
        assert mock_smtp.send_message_called is True
        assert ref == "email:ops@example.com"

    @pytest.mark.asyncio
    async def test_send_smtp_exception_raises_connection_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SMTPException raises DeliveryError with reason=connection_error."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_FROM", "alerts@example.com")
        get_settings.cache_clear()

        mock_smtp = MockSMTP("smtp.example.com", 587)
        mock_smtp.should_raise = smtplib.SMTPException("Connection refused")

        def smtp_factory(host: str, port: int) -> MockSMTP:
            return mock_smtp

        monkeypatch.setattr(email_module.smtplib, "SMTP", smtp_factory)

        channel = EmailChannel()
        _, server, rule, alert = _make_tenant_server_rule_alert()
        channel_config = {"to": ["ops@example.com"]}

        with pytest.raises(DeliveryError) as exc:
            await channel.send(alert=alert, rule=rule, server=server, channel_config=channel_config)

        assert exc.value.reason == "connection_error"
        assert "Connection refused" in exc.value.message

    @pytest.mark.asyncio
    async def test_send_os_error_raises_connection_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OSError raises DeliveryError with reason=connection_error."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_FROM", "alerts@example.com")
        get_settings.cache_clear()

        mock_smtp = MockSMTP("smtp.example.com", 587)
        mock_smtp.should_raise = OSError("Network unreachable")

        def smtp_factory(host: str, port: int) -> MockSMTP:
            return mock_smtp

        monkeypatch.setattr(email_module.smtplib, "SMTP", smtp_factory)

        channel = EmailChannel()
        _, server, rule, alert = _make_tenant_server_rule_alert()
        channel_config = {"to": ["ops@example.com"]}

        with pytest.raises(DeliveryError) as exc:
            await channel.send(alert=alert, rule=rule, server=server, channel_config=channel_config)

        assert exc.value.reason == "connection_error"
        assert "Network unreachable" in exc.value.message

    @pytest.mark.asyncio
    async def test_send_with_none_server_includes_null_in_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When server is None, body doesn't include server details."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_FROM", "alerts@example.com")
        get_settings.cache_clear()

        mock_smtp = MockSMTP("smtp.example.com", 587)

        def smtp_factory(host: str, port: int) -> MockSMTP:
            return mock_smtp

        monkeypatch.setattr(email_module.smtplib, "SMTP", smtp_factory)

        channel = EmailChannel()
        tenant = Tenant(name="test-tenant", slug=f"test-{uuid4().hex[:8]}")
        rule = AlertRule(
            tenant_id=tenant.id,
            entity_type=EntityType.SERVER,
            entity_id=None,
            metric="cpu_usage",
            operator=AlertOperator.GT,
            threshold=80.0,
            duration_s=60,
            severity=AlertSeverity.WARNING,
            channels={"email": {"to": ["ops@example.com"]}},
            is_active=True,
        )
        alert = Alert(
            rule_id=rule.id,
            server_id=None,
            tenant_id=tenant.id,
            severity=AlertSeverity.WARNING,
            status=AlertStatus.OPEN,
            message="cpu_usage > 80 sustained >= 60s",
            triggered_at=datetime.now(UTC),
            value_at_trigger=85.0,
        )
        channel_config = {"to": ["ops@example.com"]}

        await channel.send(alert=alert, rule=rule, server=None, channel_config=channel_config)

        sent_msg = mock_smtp.sent_message
        assert sent_msg is not None
        parsed = email_lib.message_from_string(sent_msg)
        # Subject should include rule.id since server is None
        assert f"on {rule.id}" in parsed["Subject"]
        # Body should not have hostname/ip/os lines
        body = parsed.get_payload(decode=True)
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        assert "Hostname: N/A" in body or "Hostname:" not in body


class TestChannelRegistry:
    """Tests for channel registry with email channel."""

    def test_get_channel_email_returns_registered_channel(self) -> None:
        """get_channel('email') returns the registered EmailChannel."""
        channel = get_channel("email")
        assert isinstance(channel, EmailChannel)
        assert channel.name == "email"
