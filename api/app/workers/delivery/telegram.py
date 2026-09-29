"""Telegram delivery channel for alert notifications via the Bot API."""

from __future__ import annotations

from datetime import datetime

import httpx

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.alert import Alert, AlertRule
from app.models.server import Server
from app.workers.delivery import DeliveryError, register

logger = get_logger(__name__)

_SEVERITY_LABEL = {
    "info": "INFO",
    "warning": "WARNING",
    "critical": "CRITICAL",
}


class TelegramChannel:
    """Telegram delivery channel — sends alert text via the Bot API sendMessage."""

    name = "telegram"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Initialize the Telegram channel.

        Args:
            client: Optional httpx.AsyncClient for test injection.
                   Defaults to a new client with 10s timeout.
        """
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def send(
        self,
        *,
        alert: Alert,
        rule: AlertRule | None,
        server: Server | None,
        channel_config: dict,
    ) -> str:
        """Send alert via Telegram sendMessage.

        Args:
            alert: The alert to deliver.
            rule: The rule that triggered the alert, or None for job-failure
                alerts that have no associated AlertRule.
            server: The server associated with the alert, or None.
            channel_config: Must contain "chat_id"; optional "thread_id" for
                forum topics and "silent" to suppress the notification sound.

        Returns:
            External reference: "telegram:{message_id}".

        Raises:
            DeliveryError: On missing config, Telegram not configured, HTTP
                error, timeout, or connection error.
        """
        chat_id = channel_config.get("chat_id")
        if chat_id is None or str(chat_id).strip() == "":
            raise DeliveryError(
                message="Telegram channel config missing required 'chat_id'",
                reason="config_missing",
            )

        settings = get_settings()
        if not settings.telegram_enabled:
            raise DeliveryError(
                message="Telegram bot token not configured",
                reason="config_missing",
            )

        text = self._build_text(alert, rule, server, settings)
        payload: dict[str, object] = {"chat_id": chat_id, "text": text}
        if channel_config.get("thread_id") is not None:
            payload["message_thread_id"] = channel_config["thread_id"]
        if channel_config.get("silent"):
            payload["disable_notification"] = True

        url = f"{settings.TELEGRAM_API_BASE.rstrip('/')}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"

        try:
            response = await self._client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            logger.warning(
                "telegram_timeout",
                alert_id=str(alert.id),
                error=str(exc),
            )
            raise DeliveryError(
                message="Telegram request timed out",
                reason="timeout",
            ) from exc
        except httpx.RequestError as exc:
            logger.warning(
                "telegram_connection_error",
                alert_id=str(alert.id),
                error=str(exc),
            )
            raise DeliveryError(
                message=f"Telegram connection error: {exc}",
                reason="connection_error",
            ) from exc

        if not response.is_success:
            description = _extract_description(response)
            logger.warning(
                "telegram_http_error",
                alert_id=str(alert.id),
                status_code=response.status_code,
                description=description,
            )
            raise DeliveryError(
                message=f"Telegram responded {response.status_code}: {description}",
                reason="http_error",
            )

        body = response.json()
        if not body.get("ok"):
            description = body.get("description") or "unknown error"
            logger.warning(
                "telegram_api_error",
                alert_id=str(alert.id),
                error_code=body.get("error_code"),
                description=description,
            )
            raise DeliveryError(
                message=f"Telegram API error: {description}",
                reason="http_error",
            )

        message_id = body.get("result", {}).get("message_id")
        external_ref = f"telegram:{message_id}" if message_id is not None else f"telegram:{alert.id}"
        logger.info(
            "telegram_delivered",
            alert_id=str(alert.id),
            chat_id=str(chat_id),
            external_ref=external_ref,
        )
        return external_ref

    def _build_text(
        self,
        alert: Alert,
        rule: AlertRule | None,
        server: Server | None,
        settings: Settings,
    ) -> str:
        """Build the plain-text message body, truncated to the API limit."""
        source = "job" if rule is None else "rule"
        lines = [
            f"[{_SEVERITY_LABEL.get(alert.severity.value, alert.severity.value.upper())}] SPSAAS alert",
            f"Source: {source}",
        ]
        if server is not None:
            lines.append(f"Server: {server.hostname} ({server.os})")
        lines.append(f"Message: {alert.message}")
        lines.append(f"Value at trigger: {alert.value_at_trigger}")
        if rule is not None:
            lines.append(f"Rule: {rule.metric} {rule.operator.value} {rule.threshold}")
        else:
            lines.append("Rule: none (job failure)")
        lines.append(f"Alert id: {alert.id}")
        lines.append(f"Triggered at: {_iso_utc(alert.triggered_at)}")

        text = "\n".join(lines)
        limit = settings.TELEGRAM_MAX_MESSAGE_CHARS
        if len(text) <= limit:
            return text

        return self._build_truncated(len(text), limit, settings)

    def _build_truncated(self, original_length: int, limit: int, settings: Settings) -> str:
        """Replace an over-long body with a short pointer to the dashboard."""
        dashboard_url = settings.PUBLIC_DASHBOARD_URL
        if dashboard_url:
            pointer = f"Alert message too long to display here. See the full detail at {dashboard_url.rstrip('/')}/alertas"
        else:
            pointer = "Alert message too long to display here. See the full detail in the SPSAAS web dashboard."

        # Guarantee the pointer itself fits even if a pathological URL is set.
        if len(pointer) >= limit:
            pointer = "Alert message too long to display here. See the full detail in the SPSAAS web dashboard."

        header = f"[{original_length} chars, limit {limit}]"
        return f"{header}\n{pointer}"

    async def close(self) -> None:
        """Close the underlying HTTP client if owned by this channel."""
        if self._owns_client:
            await self._client.aclose()


def _extract_description(response: httpx.Response) -> str:
    """Best-effort human-readable description of a failed Telegram response."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict) and body.get("description"):
        return str(body["description"])
    return response.text[:200]


def _iso_utc(value: datetime) -> str:
    """Render a datetime as ISO-8601 with a Z suffix."""
    return value.isoformat().replace("+00:00", "Z")


# Auto-register on import
register(TelegramChannel())
