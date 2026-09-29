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
from app.models.alert import Alert, AlertDelivery, AlertRule
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


def _mark_failed(delivery: AlertDelivery, error: str) -> None:
    """Marca un delivery como fallido y limpia sus campos de resultado.

    Un delivery fallido no se vuelve a seleccionar (el runner solo procesa
    status='pending'), por lo que este estado es terminal.
    """
    delivery.status = "failed"
    delivery.error = error
    delivery.external_ref = None
    delivery.delivered_at = None


@dataclass(frozen=True, slots=True)
class _DeliveryContext:
    """Relaciones resueltas de un delivery, ya validadas."""

    alert: Alert
    rule: AlertRule | None
    server: Server | None


def _resolve_context(delivery: AlertDelivery) -> _DeliveryContext:
    """Resuelve alerta, regla y servidor de un delivery.

    Raises:
        DeliveryError: Si el delivery no tiene alerta asociada.
    """
    alert = delivery.alert
    if alert is None:
        raise DeliveryError(f"delivery {delivery.id} has no alert", "alert_missing")
    return _DeliveryContext(alert=alert, rule=alert.rule, server=None)


def _log_delivery_failed(delivery: AlertDelivery, channel: str, reason: str) -> None:
    """Log estructurado de un delivery fallido, sin datos de la alerta."""
    logger.warning(
        "delivery_failed",
        delivery_id=str(delivery.id),
        channel=channel,
        reason=reason,
        error=format_exc(),
    )


async def deliver_alerts(session: AsyncSession) -> DeliveryRunSummary:
    """Procesa todas las entregas pendientes de todos los tenants.

    Para cada delivery:
      - Resuelve alerta, regla y servidor (si aplica).
      - Obtiene la configuración del canal: primero desde delivery.config
        (snapshot en creación), luego fallback a rule.channels si existe.
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
        channel_name = delivery.channel

        # Resolver alerta/regla/servidor puede lanzar (FK colgante, cascade
        # incompleto, carga lazy). Eso debe marcar SOLO este delivery como
        # failed y continuar el lote, nunca abortar el runner completo.
        try:
            context = _resolve_context(delivery)
            alert = context.alert
            rule = context.rule
            server = context.server
            if alert.server_id is not None:
                server = await session.get(Server, alert.server_id)
        except DeliveryError as e:
            _mark_failed(delivery, f"unresolved: {e.reason}: {e.message}")
            summary = DeliveryRunSummary(sent=summary.sent, failed=summary.failed + 1)
            _log_delivery_failed(delivery, channel_name, "unresolved")
            continue
        except Exception as e:  # noqa: BLE001
            _mark_failed(delivery, f"unresolved: {type(e).__name__}: {e}")
            summary = DeliveryRunSummary(sent=summary.sent, failed=summary.failed + 1)
            _log_delivery_failed(delivery, channel_name, "unresolved")
            continue

        try:
            # Resolver configuración de canal: snapshot en delivery.config tiene prioridad,
            # fallback a rule.channels para filas legacy (config=NULL) cuando rule existe.
            channel_config = delivery.config
            if channel_config is None and rule is not None:
                channel_config = (rule.channels or {}).get(channel_name)

            # Configuración de canal faltante (ni snapshot ni rule.channels)
            if channel_config is None:
                _mark_failed(delivery, "config_missing: channel not configured in rule")
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
            _mark_failed(delivery, f"{e.reason}: {e.message}")
            summary = DeliveryRunSummary(sent=summary.sent, failed=summary.failed + 1)
            logger.warning(
                "delivery_failed",
                delivery_id=str(delivery.id),
                alert_id=str(alert.id),
                channel=channel_name,
                tenant_id=str(alert.tenant_id),
                reason=e.reason,
            )

        except Exception as e:  # noqa: BLE001
            # Cualquier otro error: nunca crashea el runner completo
            _mark_failed(delivery, f"unexpected: {type(e).__name__}: {e}")
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
