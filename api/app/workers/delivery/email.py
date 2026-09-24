"""Email delivery channel for alert notifications via SMTP."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.alert import Alert, AlertRule
from app.models.server import Server
from app.workers.delivery import DeliveryError, register

logger = get_logger(__name__)


class EmailChannel:
    """Email delivery channel — sends alert via SMTP using stdlib."""

    name = "email"

    async def send(
        self,
        *,
        alert: Alert,
        rule: AlertRule,
        server: Server | None,
        channel_config: dict,
    ) -> str:
        """Send alert via SMTP.

        Args:
            alert: The alert to deliver.
            rule: The rule that triggered the alert.
            server: The server associated with the alert, or None.
            channel_config: Must contain "to" key with list of email addresses.

        Returns:
            External reference: "email:{comma_separated_recipients}".

        Raises:
            DeliveryError: On missing config, SMTP not configured, or SMTP errors.
        """
        to_emails = channel_config.get("to")
        if not to_emails or not isinstance(to_emails, list) or len(to_emails) == 0:
            raise DeliveryError(
                message="Email channel config missing required 'to' list",
                reason="config_missing",
            )

        settings = get_settings()
        if not settings.smtp_enabled:
            raise DeliveryError(
                message="SMTP not configured",
                reason="config_missing",
            )

        msg = self._build_message(alert, rule, server, to_emails, settings)

        try:
            await asyncio.to_thread(self._send_smtp, msg, settings)
        except smtplib.SMTPException as exc:
            logger.warning(
                "email_smtp_error",
                alert_id=str(alert.id),
                error=str(exc),
            )
            raise DeliveryError(
                message=f"SMTP error: {exc}",
                reason="connection_error",
            ) from exc
        except OSError as exc:
            logger.warning(
                "email_connection_error",
                alert_id=str(alert.id),
                error=str(exc),
            )
            raise DeliveryError(
                message=f"SMTP connection error: {exc}",
                reason="connection_error",
            ) from exc

        external_ref = f"email:{','.join(to_emails)}"
        logger.info(
            "email_delivered",
            alert_id=str(alert.id),
            to=to_emails,
            external_ref=external_ref,
        )
        return external_ref

    def _build_message(
        self,
        alert: Alert,
        rule: AlertRule,
        server: Server | None,
        to_emails: list[str],
        settings: Settings,
    ) -> EmailMessage:
        """Build the EmailMessage for the alert."""
        msg = EmailMessage()
        msg["From"] = settings.SMTP_FROM
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = (
            f"[SPSAAS] ALERT {alert.severity.value.upper()} "
            f"{rule.metric} on {server.hostname if server else rule.id}"
        )

        triggered_at_iso = alert.triggered_at.isoformat().replace("+00:00", "Z")

        server_lines = []
        if server:
            server_lines = [
                f"  Hostname: {server.hostname}",
                f"  IP: {server.ip or 'N/A'}",
                f"  OS: {server.os or 'N/A'}",
            ]

        body = "\n".join(
            [
                "SPSAAS Alert Notification",
                "=" * 40,
                "",
                f"Alert ID: {alert.id}",
                f"Severity: {alert.severity.value}",
                f"Status: {alert.status.value}",
                f"Message: {alert.message}",
                f"Value at Trigger: {alert.value_at_trigger}",
                f"Triggered At: {triggered_at_iso}",
                "",
                "Rule:",
                f"  ID: {rule.id}",
                f"  Metric: {rule.metric}",
                f"  Operator: {rule.operator.value}",
                f"  Threshold: {rule.threshold}",
                f"  Duration: {rule.duration_s}s",
                f"  Severity: {rule.severity.value}",
                "",
                "Server:",
                *server_lines,
                "",
                "—",
                "This is an automated message from SPSAAS monitoring.",
            ]
        )

        msg.set_content(body)
        return msg

    def _send_smtp(self, msg: EmailMessage, settings: Settings) -> None:
        """Send the email via SMTP (blocking, runs in thread)."""
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
            if settings.SMTP_STARTTLS:
                smtp.starttls()
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)


# Auto-register on import
register(EmailChannel())
