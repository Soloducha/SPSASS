"""Shared helpers for creating alert deliveries.

This module extracts the duplicated delivery-creation logic from
``alerts.py`` and ``jobs.py`` into a single synchronous function.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertDelivery


def create_pending_deliveries(
    session: AsyncSession,
    alert_id: UUID,
    tenant_id: UUID,
    channels: dict[str, dict] | None,
) -> None:
    """Create pending ``AlertDelivery`` rows for each channel.

    Each delivery snapshots the channel config at creation time. This is
    the whole point of ``AlertDelivery.config`` — the snapshot semantics
    ensure that subsequent changes to the source channels mapping do not
    affect already-created deliveries.

    Args:
        session: The async database session.
        alert_id: The ID of the alert to associate deliveries with.
        tenant_id: The tenant ID for scoping.
        channels: Mapping of channel name to channel config. Falsy values
            (``None``, ``{}``) produce zero deliveries. Keys are iterated
            in sorted order for deterministic delivery ordering.
    """
    channels = channels or {}
    for channel in sorted(set(channels.keys())):
        delivery = AlertDelivery(
            alert_id=alert_id,
            channel=channel,
            status="pending",
            tenant_id=tenant_id,
            config=channels.get(channel),
        )
        session.add(delivery)
