"""Webhook delivery channel for alert notifications."""

from __future__ import annotations

import httpx

from app.core.logging import get_logger
from app.models.alert import Alert, AlertRule
from app.models.server import Server
from app.workers.delivery import DeliveryError, register

logger = get_logger(__name__)


class WebhookChannel:
    """Webhook delivery channel — sends alert payload via HTTP POST."""

    name = "webhook"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Initialize the webhook channel.

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
        rule: AlertRule,
        server: Server | None,
        channel_config: dict,
    ) -> str:
        """Send alert via webhook POST.

        Args:
            alert: The alert to deliver.
            rule: The rule that triggered the alert.
            server: The server associated with the alert, or None.
            channel_config: Must contain "url" key; optional "headers" dict.

        Returns:
            External reference: X-Request-Id header if present,
            otherwise "webhook:{alert.id}".

        Raises:
            DeliveryError: On missing config, HTTP error, timeout, or connection error.
        """
        url = channel_config.get("url")
        if not url:
            raise DeliveryError(
                message="Webhook channel config missing required 'url'",
                reason="config_missing",
            )

        headers = channel_config.get("headers", {})
        headers["Content-Type"] = "application/json"

        payload = self._build_payload(alert, rule, server)

        try:
            response = await self._client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            logger.warning(
                "webhook_timeout",
                url=url,
                alert_id=str(alert.id),
                error=str(exc),
            )
            raise DeliveryError(
                message="Webhook request timed out",
                reason="timeout",
            ) from exc
        except httpx.RequestError as exc:
            logger.warning(
                "webhook_connection_error",
                url=url,
                alert_id=str(alert.id),
                error=str(exc),
            )
            raise DeliveryError(
                message=f"Webhook connection error: {exc}",
                reason="connection_error",
            ) from exc

        if response.is_success:
            external_ref = response.headers.get("X-Request-Id") or f"webhook:{alert.id}"
            logger.info(
                "webhook_delivered",
                url=url,
                alert_id=str(alert.id),
                external_ref=external_ref,
                status_code=response.status_code,
            )
            return external_ref

        logger.warning(
            "webhook_http_error",
            url=url,
            alert_id=str(alert.id),
            status_code=response.status_code,
            response_text=response.text[:500],
        )
        raise DeliveryError(
            message=f"Webhook responded {response.status_code}",
            reason="http_error",
        )

    def _build_payload(self, alert: Alert, rule: AlertRule, server: Server | None) -> dict:
        """Build the JSON payload for the webhook."""
        return {
            "alert": {
                "id": str(alert.id),
                "severity": alert.severity.value,
                "status": alert.status.value,
                "message": alert.message,
                "value_at_trigger": alert.value_at_trigger,
                "triggered_at": alert.triggered_at.isoformat().replace("+00:00", "Z"),
            },
            "rule": {
                "id": str(rule.id),
                "metric": rule.metric,
                "operator": rule.operator.value,
                "threshold": rule.threshold,
                "duration_s": rule.duration_s,
                "severity": rule.severity.value,
            },
            "server": (
                {
                    "id": str(server.id),
                    "hostname": server.hostname,
                    "ip": server.ip,
                    "os": server.os,
                }
                if server is not None
                else None
            ),
        }

    async def close(self) -> None:
        """Close the underlying HTTP client if owned by this channel."""
        if self._owns_client:
            await self._client.aclose()


# Auto-register on import
register(WebhookChannel())
