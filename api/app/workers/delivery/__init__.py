"""Delivery channel abstraction for alert notifications."""

from __future__ import annotations

from typing import Protocol

from app.models.alert import Alert, AlertRule
from app.models.server import Server


class DeliveryError(Exception):
    """Error raised when a delivery channel fails to send.

    Attributes:
        message: Human-readable error description.
        reason: Machine-readable reason code.
            One of: "http_error", "timeout", "connection_error",
            "config_missing", "unknown_channel".
    """

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason

    def __str__(self) -> str:
        return f"{self.reason}: {self.message}"


class DeliveryChannel(Protocol):
    """Protocol for alert delivery channels."""

    name: str

    async def send(
        self,
        *,
        alert: Alert,
        rule: AlertRule,
        server: Server | None,
        channel_config: dict,
    ) -> str:
        """Send an alert delivery.

        Args:
            alert: The alert to deliver.
            rule: The rule that triggered the alert.
            server: The server associated with the alert, or None.
            channel_config: Channel-specific configuration from rule.channels.

        Returns:
            External reference string (e.g., message ID, request ID).

        Raises:
            DeliveryError: On any delivery failure.
        """
        ...


# Channel registry
_CHANNELS: dict[str, DeliveryChannel] = {}


def register(channel: DeliveryChannel) -> None:
    """Register a delivery channel.

    Args:
        channel: Channel instance implementing DeliveryChannel.
    """
    _CHANNELS[channel.name] = channel


def get_channel(name: str) -> DeliveryChannel:
    """Get a registered delivery channel by name.

    Args:
        name: Channel name (e.g., "webhook", "email").

    Returns:
        The registered DeliveryChannel instance.

    Raises:
        DeliveryError: If channel is not registered (reason="unknown_channel").
    """
    channel = _CHANNELS.get(name)
    if channel is None:
        raise DeliveryError(
            message=f"Unknown delivery channel: {name}",
            reason="unknown_channel",
        )
    return channel


# Import webhook channel to trigger auto-registration
from app.workers.delivery import webhook  # noqa: E402,F401
