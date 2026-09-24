"""Runner de entregas de alertas (T4).

Carga todas las AlertDelivery pendientes cross-tenant, las despacha por canal
y actualiza su estado a sent/failed con external_ref, delivered_at y error.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from traceback import format_exc
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.alert import AlertDelivery
from app.models.server import Server
from app.workers.delivery import DeliveryError, get_channel

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DeliveryRunSummary:
    """Resumen de una ejecución del runner de entregas."""

    sent: int = 0
    failed: int = 0

    @property
    def total(self) -> int:
        """Total de deliveries procesados."""
        return self.sent + self.failed


async def deliver_alerts(session: AsyncSession) -> DeliveryRunSummary:
    """Procesa todas las entregas pendientes de todos los tenants.

    Para cada delivery:
      - Resuelve alerta, regla y servidor (si aplica).
      - Obtiene el canal y su configuración desde rule.channels.
      - Despacha vía canal.send().
      - Actualiza status, external_ref, delivered_at, error.
    Commit único al final. Devuelve resumen sent/failed.
    """
    summary = DeliveryRunSummary(sent=0, failed=0)
    now = datetime.now(UTC)

    # Cargar TODAS las deliveries pendientes (cross-tenant, sin RLS)
    pending_deliveries = (
        await session.scalars(
            select(AlertDelivery).where(AlertDelivery.status == "pending")
        )
    ).all()

    for delivery in pending_deliveries:
        alert = delivery.alert
        rule = alert.rule
        server = None

        # Cargar server solo si alert.server_id no es None
        if alert.server_id is not None:
            server = await session.get(Server, alert.server_id)

        channel_name = delivery.channel
        channel_config = (rule.channels or {}).get(channel_name)

        # Configuración de canal faltante en la regla
        if channel_config is None:
            delivery.status = "failed"
            delivery.error = "config_missing: channel not configured in rule"
            delivery.external_ref = None
            delivery.delivered_at = None
            summary = DeliveryRunSummary(sent=summary.sent, failed=summary.failed + 1)
            logger.warning(
                "delivery_failed",
                delivery_id=str(delivery.id),
                alert_id=str(alert.id),
                channel=channel_name,
                tenant_id=str(alert.tenant_id),
                reason="config_missing",
            )
            continue

        try:
            channel = get_channel(channel_name)
            external_ref = await channel.send(
                alert=alert,
                rule=rule,
                server=server,
                channel_config=channel_config,
            )

            # Éxito
            delivery.status = "sent"
            delivery.external_ref = external_ref
            delivery.delivered_at = now
            delivery.error = None
            summary = DeliveryRunSummary(sent=summary.sent + 1, failed=summary.failed)
            logger.info(
                "delivery_sent",
                delivery_id=str(delivery.id),
                alert_id=str(alert.id),
                channel=channel_name,
                tenant_id=str(alert.tenant_id),
                external_ref=external_ref,
            )

        except DeliveryError as e:
            # Error conocido del canal
            delivery.status = "failed"
            delivery.error = f"{e.reason}: {e.message}"
            delivery.external_ref = None
            delivery.delivered_at = None
            summary = DeliveryRunSummary(sent=summary.sent, failed=summary.failed + 1)
            logger.warning(
                "delivery_failed",
                delivery_id=str(delivery.id),
                alert_id=str(alert.id),
                channel=channel_name,
                tenant_id=str(alert.tenant_id),
                reason=e.reason,
            )

        except Exception as e:
            # Cualquier otro error: nunca crashea el runner completo
            delivery.status = "failed"
            delivery.error = f"unexpected: {type(e).__name__}: {e}"
            delivery.external_ref = None
            delivery.delivered_at = None
            summary = DeliveryRunSummary(sent=summary.sent, failed=summary.failed + 1)
            logger.warning(
                "delivery_failed",
                delivery_id=str(delivery.id),
                alert_id=str(alert.id),
                channel=channel_name,
                tenant_id=str(alert.tenant_id),
                reason="unexpected",
                error=format_exc(),
            )

    await session.commit()
    return summary
