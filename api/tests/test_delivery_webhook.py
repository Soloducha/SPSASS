"""Unit tests for Webhook delivery channel (T2)."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
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
from app.workers.delivery.webhook import WebhookChannel

# ──────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────

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
        channels={"webhook": {"url": "https://example.com/webhook"}},
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
# Tests
# ──────────────────────────────────────────────

class TestWebhookChannel:
    """Tests for WebhookChannel.send()."""

    @pytest.mark.asyncio
    async def test_send_200_with_x_request_id_returns_header_value(self) -> None:
        """200 response with X-Request-Id header returns that ref."""
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"X-Request-Id": "req-12345"},
                json={"ok": True},
            )
        )
        client = httpx.AsyncClient(transport=transport)
        channel = WebhookChannel(client=client)

        _, server, rule, alert = _make_tenant_server_rule_alert()
        channel_config = {"url": "https://example.com/webhook", "headers": {"X-Custom": "value"}}

        ref = await channel.send(alert=alert, rule=rule, server=server, channel_config=channel_config)

        assert ref == "req-12345"
        await channel.close()

    @pytest.mark.asyncio
    async def test_send_200_without_x_request_id_returns_webhook_alert_id(self) -> None:
        """200 response without X-Request-Id returns webhook:{alert.id}."""
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"ok": True})
        )
        client = httpx.AsyncClient(transport=transport)
        channel = WebhookChannel(client=client)

        _, server, rule, alert = _make_tenant_server_rule_alert()
        channel_config = {"url": "https://example.com/webhook"}

        ref = await channel.send(alert=alert, rule=rule, server=server, channel_config=channel_config)

        assert ref == f"webhook:{alert.id}"
        await channel.close()

    @pytest.mark.asyncio
    async def test_send_500_raises_delivery_error_http_error(self) -> None:
        """Non-2xx response raises DeliveryError with reason=http_error."""
        transport = httpx.MockTransport(
            lambda request: httpx.Response(500, text="Internal Server Error")
        )
        client = httpx.AsyncClient(transport=transport)
        channel = WebhookChannel(client=client)

        _, server, rule, alert = _make_tenant_server_rule_alert()
        channel_config = {"url": "https://example.com/webhook"}

        with pytest.raises(DeliveryError) as exc:
            await channel.send(alert=alert, rule=rule, server=server, channel_config=channel_config)

        assert exc.value.reason == "http_error"
        assert "500" in exc.value.message
        await channel.close()

    @pytest.mark.asyncio
    async def test_send_timeout_raises_delivery_error_timeout(self) -> None:
        """Timeout raises DeliveryError with reason=timeout."""

        def raise_timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("Request timed out")

        transport = httpx.MockTransport(raise_timeout)
        client = httpx.AsyncClient(transport=transport)
        channel = WebhookChannel(client=client)

        _, server, rule, alert = _make_tenant_server_rule_alert()
        channel_config = {"url": "https://example.com/webhook"}

        with pytest.raises(DeliveryError) as exc:
            await channel.send(alert=alert, rule=rule, server=server, channel_config=channel_config)

        assert exc.value.reason == "timeout"
        await channel.close()

    @pytest.mark.asyncio
    async def test_send_connection_error_raises_delivery_error_connection_error(self) -> None:
        """Connection error raises DeliveryError with reason=connection_error."""

        def raise_connect_error(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(raise_connect_error)
        client = httpx.AsyncClient(transport=transport)
        channel = WebhookChannel(client=client)

        _, server, rule, alert = _make_tenant_server_rule_alert()
        channel_config = {"url": "https://example.com/webhook"}

        with pytest.raises(DeliveryError) as exc:
            await channel.send(alert=alert, rule=rule, server=server, channel_config=channel_config)

        assert exc.value.reason == "connection_error"
        await channel.close()

    @pytest.mark.asyncio
    async def test_send_missing_url_raises_delivery_error_config_missing(self) -> None:
        """Missing url in channel_config raises DeliveryError with reason=config_missing."""
        transport = httpx.MockTransport(lambda request: httpx.Response(200))
        client = httpx.AsyncClient(transport=transport)
        channel = WebhookChannel(client=client)

        _, server, rule, alert = _make_tenant_server_rule_alert()
        channel_config: dict[str, str] = {}  # missing url

        with pytest.raises(DeliveryError) as exc:
            await channel.send(alert=alert, rule=rule, server=server, channel_config=channel_config)

        assert exc.value.reason == "config_missing"
        assert "url" in exc.value.message.lower()
        await channel.close()

    @pytest.mark.asyncio
    async def test_send_with_none_server_includes_null_in_payload(self) -> None:
        """When server is None, payload.server is null."""
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"ok": True})
        )
        client = httpx.AsyncClient(transport=transport)
        channel = WebhookChannel(client=client)

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
            channels={"webhook": {"url": "https://example.com/webhook"}},
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
        channel_config = {"url": "https://example.com/webhook"}

        # Capture the request to inspect payload
        captured_request: dict[str, bytes | dict[str, str]] = {}

        def capture_request(request: httpx.Request) -> httpx.Response:
            captured_request["body"] = request.content
            return httpx.Response(200, json={"ok": True})

        transport = httpx.MockTransport(capture_request)
        client = httpx.AsyncClient(transport=transport)
        channel = WebhookChannel(client=client)

        await channel.send(alert=alert, rule=rule, server=None, channel_config=channel_config)

        payload = json.loads(captured_request["body"])  # type: ignore[arg-type]
        assert payload["server"] is None
        await channel.close()

    @pytest.mark.asyncio
    async def test_send_payload_structure_matches_spec(self) -> None:
        """Payload has exact keys and value types per spec."""
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"ok": True})
        )
        client = httpx.AsyncClient(transport=transport)
        channel = WebhookChannel(client=client)

        _, server, rule, alert = _make_tenant_server_rule_alert()
        channel_config = {"url": "https://example.com/webhook", "headers": {"Authorization": "Bearer token"}}

        captured_request: dict[str, bytes | dict[str, str]] = {}

        def capture_request(request: httpx.Request) -> httpx.Response:
            captured_request["body"] = request.content
            captured_request["headers"] = {
                k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
                for k, v in request.headers.items()
            }
            return httpx.Response(200, json={"ok": True})

        transport = httpx.MockTransport(capture_request)
        client = httpx.AsyncClient(transport=transport)
        channel = WebhookChannel(client=client)

        await channel.send(alert=alert, rule=rule, server=server, channel_config=channel_config)

        payload = json.loads(captured_request["body"])  # type: ignore[arg-type]

        # Check top-level keys
        assert set(payload.keys()) == {"alert", "rule", "server"}

        # Check alert object
        assert payload["alert"]["id"] == str(alert.id)
        assert payload["alert"]["severity"] == "warning"
        assert payload["alert"]["status"] == "open"
        assert payload["alert"]["message"] == alert.message
        assert payload["alert"]["value_at_trigger"] == alert.value_at_trigger
        assert payload["alert"]["triggered_at"].endswith("Z")

        # Check rule object
        assert payload["rule"]["id"] == str(rule.id)
        assert payload["rule"]["metric"] == rule.metric
        assert payload["rule"]["operator"] == "gt"
        assert payload["rule"]["threshold"] == rule.threshold
        assert payload["rule"]["duration_s"] == rule.duration_s
        assert payload["rule"]["severity"] == "warning"

        # Check server object
        assert payload["server"]["id"] == str(server.id)
        assert payload["server"]["hostname"] == server.hostname
        assert payload["server"]["ip"] == server.ip
        assert payload["server"]["os"] == server.os

        # Check custom headers were passed
        headers = captured_request["headers"]
        assert isinstance(headers, dict)
        assert headers["authorization"] == "Bearer token"
        assert headers["content-type"] == "application/json"

        await channel.close()


class TestChannelRegistry:
    """Tests for channel registry (get_channel, register)."""

    def test_get_channel_unknown_raises_delivery_error_unknown_channel(self) -> None:
        """get_channel('nope') raises DeliveryError with reason=unknown_channel."""
        with pytest.raises(DeliveryError) as exc:
            get_channel("nope")
        assert exc.value.reason == "unknown_channel"
        assert "nope" in exc.value.message

    def test_get_channel_webhook_returns_registered_channel(self) -> None:
        """get_channel('webhook') returns the registered WebhookChannel."""
        channel = get_channel("webhook")
        assert isinstance(channel, WebhookChannel)
        assert channel.name == "webhook"
