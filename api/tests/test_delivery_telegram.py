"""Unit tests for Telegram delivery channel."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from app.api.v1.schemas import AlertRuleCreate
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
from app.workers.delivery.telegram import TelegramChannel
from pydantic import ValidationError

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
        channels={"telegram": {"chat_id": "-1001234567890"}},
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


def _make_job_alert() -> tuple[Tenant, Server, Alert]:
    """Create a job-failure alert: no rule, no server."""
    tenant = Tenant(name="test-tenant", slug=f"test-{uuid4().hex[:8]}")
    alert = Alert(
        rule_id=None,
        server_id=None,
        tenant_id=tenant.id,
        severity=AlertSeverity.CRITICAL,
        status=AlertStatus.OPEN,
        message="job nightly-backup failed with exit code 1",
        triggered_at=datetime.now(UTC),
        value_at_trigger=1.0,
    )
    return tenant, None, alert  # type: ignore[return-value]


def _transport_returning(status: int, json_body: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=json_body, request=request)

    return httpx.MockTransport(handler)


def _ok_body(message_id: int = 555) -> dict:
    return {"ok": True, "result": {"message_id": message_id}}


def _enable_telegram(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


# ──────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────

class TestTelegramRegistration:
    """The channel must be discoverable through the registry."""

    def test_telegram_is_registered(self) -> None:
        assert get_channel("telegram").name == "telegram"


class TestTelegramConfig:
    """Config validation and gating."""

    @pytest.mark.asyncio
    async def test_missing_chat_id_raises_config_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_telegram(monkeypatch)
        channel = TelegramChannel()
        _, server, rule, alert = _make_tenant_server_rule_alert()

        with pytest.raises(DeliveryError) as exc:
            await channel.send(alert=alert, rule=rule, server=server, channel_config={})

        assert exc.value.reason == "config_missing"
        assert "chat_id" in exc.value.message

    @pytest.mark.asyncio
    async def test_blank_chat_id_raises_config_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_telegram(monkeypatch)
        channel = TelegramChannel()
        _, server, rule, alert = _make_tenant_server_rule_alert()

        with pytest.raises(DeliveryError) as exc:
            await channel.send(
                alert=alert, rule=rule, server=server, channel_config={"chat_id": "   "}
            )

        assert exc.value.reason == "config_missing"

    @pytest.mark.asyncio
    async def test_token_not_configured_raises_config_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
        get_settings.cache_clear()
        channel = TelegramChannel()
        _, server, rule, alert = _make_tenant_server_rule_alert()

        with pytest.raises(DeliveryError) as exc:
            await channel.send(
                alert=alert, rule=rule, server=server, channel_config={"chat_id": "123"}
            )

        assert exc.value.reason == "config_missing"
        assert "bot token" in exc.value.message


class TestTelegramSend:
    """Successful delivery path."""

    @pytest.mark.asyncio
    async def test_send_success_returns_message_id_reference(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_telegram(monkeypatch)
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json=_ok_body(778), request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        channel = TelegramChannel(client=client)
        _, server, rule, alert = _make_tenant_server_rule_alert()

        ref = await channel.send(
            alert=alert, rule=rule, server=server, channel_config={"chat_id": "-100999"}
        )

        assert ref == "telegram:778"
        assert len(captured) == 1
        assert "/bot123:ABC/sendMessage" in str(captured[0].url)
        await client.aclose()

    @pytest.mark.asyncio
    async def test_payload_carries_alert_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_telegram(monkeypatch)
        bodies: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json=_ok_body(), request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        channel = TelegramChannel(client=client)
        _, server, rule, alert = _make_tenant_server_rule_alert()

        await channel.send(
            alert=alert, rule=rule, server=server, channel_config={"chat_id": "42"}
        )

        body = bodies[0]
        assert body["chat_id"] == "42"
        assert "WARNING" in body["text"]
        assert "cpu_usage" in body["text"]
        assert "test-server" in body["text"]
        # No parse_mode: the user chose plain text deliberately.
        assert "parse_mode" not in body
        await client.aclose()

    @pytest.mark.asyncio
    async def test_job_alert_renders_without_rule(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_telegram(monkeypatch)
        bodies: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json=_ok_body(), request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        channel = TelegramChannel(client=client)
        _, server, alert = _make_job_alert()

        ref = await channel.send(
            alert=alert, rule=None, server=server, channel_config={"chat_id": "42"}
        )

        assert ref.startswith("telegram:")
        assert "job" in bodies[0]["text"]
        assert "none (job failure)" in bodies[0]["text"]
        await client.aclose()

    @pytest.mark.asyncio
    async def test_thread_id_and_silent_are_forwarded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_telegram(monkeypatch)
        bodies: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json=_ok_body(), request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        channel = TelegramChannel(client=client)
        _, server, rule, alert = _make_tenant_server_rule_alert()

        await channel.send(
            alert=alert,
            rule=rule,
            server=server,
            channel_config={"chat_id": "42", "thread_id": 7, "silent": True},
        )

        assert bodies[0]["message_thread_id"] == 7
        assert bodies[0]["disable_notification"] is True
        await client.aclose()

    @pytest.mark.asyncio
    async def test_missing_message_id_falls_back_to_alert_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_telegram(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ok": True, "result": {}}, request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        channel = TelegramChannel(client=client)
        _, server, rule, alert = _make_tenant_server_rule_alert()

        ref = await channel.send(
            alert=alert, rule=rule, server=server, channel_config={"chat_id": "42"}
        )

        assert ref == f"telegram:{alert.id}"
        await client.aclose()


class TestTelegramTruncation:
    """The 4096-char API limit."""

    @pytest.mark.asyncio
    async def test_long_message_is_replaced_by_pointer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_telegram(monkeypatch, PUBLIC_DASHBOARD_URL="https://spsaas.example.com")
        bodies: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json=_ok_body(), request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        channel = TelegramChannel(client=client)
        _, server, rule, alert = _make_tenant_server_rule_alert()
        alert.message = "x" * 6000

        await channel.send(
            alert=alert, rule=rule, server=server, channel_config={"chat_id": "42"}
        )

        text = bodies[0]["text"]
        assert len(text) < 6000
        assert "too long" in text
        assert "https://spsaas.example.com/alertas" in text
        await client.aclose()

    @pytest.mark.asyncio
    async def test_pointer_without_dashboard_url_has_no_link(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_telegram(monkeypatch, PUBLIC_DASHBOARD_URL="")
        bodies: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json=_ok_body(), request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        channel = TelegramChannel(client=client)
        _, server, rule, alert = _make_tenant_server_rule_alert()
        alert.message = "y" * 6000

        await channel.send(
            alert=alert, rule=rule, server=server, channel_config={"chat_id": "42"}
        )

        text = bodies[0]["text"]
        assert "too long" in text
        assert "http" not in text
        assert "web dashboard" in text
        await client.aclose()

    @pytest.mark.asyncio
    async def test_message_under_limit_is_sent_whole(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_telegram(monkeypatch)
        bodies: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json=_ok_body(), request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        channel = TelegramChannel(client=client)
        _, server, rule, alert = _make_tenant_server_rule_alert()
        alert.message = "disk almost full on /var/lib"

        await channel.send(
            alert=alert, rule=rule, server=server, channel_config={"chat_id": "42"}
        )

        text = bodies[0]["text"]
        assert "disk almost full on /var/lib" in text
        assert "too long" not in text
        await client.aclose()


class TestTelegramErrors:
    """Failure mapping to DeliveryError reason codes."""

    @pytest.mark.asyncio
    async def test_http_error_raises_http_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_telegram(monkeypatch)
        client = httpx.AsyncClient(
            transport=_transport_returning(400, {"ok": False, "description": "chat not found"})
        )
        channel = TelegramChannel(client=client)
        _, server, rule, alert = _make_tenant_server_rule_alert()

        with pytest.raises(DeliveryError) as exc:
            await channel.send(
                alert=alert, rule=rule, server=server, channel_config={"chat_id": "42"}
            )

        assert exc.value.reason == "http_error"
        assert "chat not found" in exc.value.message
        await client.aclose()

    @pytest.mark.asyncio
    async def test_api_ok_false_with_200_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_telegram(monkeypatch)
        client = httpx.AsyncClient(
            transport=_transport_returning(200, {"ok": False, "description": "chat not found"})
        )
        channel = TelegramChannel(client=client)
        _, server, rule, alert = _make_tenant_server_rule_alert()

        with pytest.raises(DeliveryError) as exc:
            await channel.send(
                alert=alert, rule=rule, server=server, channel_config={"chat_id": "42"}
            )

        assert exc.value.reason == "http_error"
        assert "chat not found" in exc.value.message
        await client.aclose()

    @pytest.mark.asyncio
    async def test_timeout_raises_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable_telegram(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        channel = TelegramChannel(client=client)
        _, server, rule, alert = _make_tenant_server_rule_alert()

        with pytest.raises(DeliveryError) as exc:
            await channel.send(
                alert=alert, rule=rule, server=server, channel_config={"chat_id": "42"}
            )

        assert exc.value.reason == "timeout"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_connection_error_raises_connection_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_telegram(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        channel = TelegramChannel(client=client)
        _, server, rule, alert = _make_tenant_server_rule_alert()

        with pytest.raises(DeliveryError) as exc:
            await channel.send(
                alert=alert, rule=rule, server=server, channel_config={"chat_id": "42"}
            )

        assert exc.value.reason == "connection_error"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_non_json_error_body_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_telegram(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(502, text="<html>bad gateway</html>", request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        channel = TelegramChannel(client=client)
        _, server, rule, alert = _make_tenant_server_rule_alert()

        with pytest.raises(DeliveryError) as exc:
            await channel.send(
                alert=alert, rule=rule, server=server, channel_config={"chat_id": "42"}
            )

        assert exc.value.reason == "http_error"
        assert "bad gateway" in exc.value.message
        await client.aclose()


class TestTelegramSchema:
    """API-level channel validation."""

    def test_telegram_channel_is_accepted(self) -> None:
        rule = AlertRuleCreate(
            entity_type=EntityType.SERVER,
            metric="cpu_usage",
            operator=AlertOperator.GT,
            threshold=80.0,
            channels={"telegram": {"chat_id": "-1001234567890"}},
        )

        # Unset optional fields are omitted rather than stored as null, so the
        # stored channel config carries only what the operator actually set.
        assert rule.channels["telegram"] == {"chat_id": "-1001234567890"}

    def test_telegram_thread_id_and_silent_normalized(self) -> None:
        rule = AlertRuleCreate(
            entity_type=EntityType.SERVER,
            metric="cpu_usage",
            operator=AlertOperator.GT,
            threshold=80.0,
            channels={"telegram": {"chat_id": "1", "thread_id": 9, "silent": True}},
        )

        assert rule.channels["telegram"]["thread_id"] == 9
        assert rule.channels["telegram"]["silent"] is True

    def test_telegram_requires_chat_id(self) -> None:
        with pytest.raises(ValidationError):
            AlertRuleCreate(
                entity_type=EntityType.SERVER,
                metric="cpu_usage",
                operator=AlertOperator.GT,
                threshold=80.0,
                channels={"telegram": {"thread_id": 9}},
            )
