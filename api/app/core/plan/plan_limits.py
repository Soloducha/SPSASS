"""Configuración de límites por plan de suscripción (Plan Gates).

Centraliza todos los límites para que sean fáciles de mantener y testear.
"""

from __future__ import annotations

from typing import Final

from app.models.tenant import PlanType

# ──────────────────────────────────────────────
# Límites por plan
# ──────────────────────────────────────────────

# Servidores máximos por tenant
MAX_SERVERS: Final[dict[PlanType, int | None]] = {
    PlanType.FREE: 3,
    PlanType.STARTER: 10,
    PlanType.GROWTH: 50,
    PlanType.ENTERPRISE: None,  # None = ilimitado
}

# API Keys máximas por tenant
MAX_API_KEYS: Final[dict[PlanType, int | None]] = {
    PlanType.FREE: 1,
    PlanType.STARTER: 5,
    PlanType.GROWTH: 20,
    PlanType.ENTERPRISE: None,
}

# Reportes por mes por tenant
MAX_REPORTS_PER_MONTH: Final[dict[PlanType, int | None]] = {
    PlanType.FREE: 1,
    PlanType.STARTER: 5,
    PlanType.GROWTH: 20,
    PlanType.ENTERPRISE: None,
}

# Canales de alerta permitidos por plan
ALLOWED_ALERT_CHANNELS: Final[dict[PlanType, set[str]]] = {
    PlanType.FREE: {"email"},
    PlanType.STARTER: {"email", "telegram"},
    PlanType.GROWTH: {"email", "telegram", "whatsapp"},
    PlanType.ENTERPRISE: {"email", "telegram", "whatsapp", "webhook", "slack", "pagerduty"},
}

# Retención de métricas en días por plan
METRICS_RETENTION_DAYS: Final[dict[PlanType, int]] = {
    PlanType.FREE: 7,
    PlanType.STARTER: 30,
    PlanType.GROWTH: 90,
    PlanType.ENTERPRISE: 365,
}

# Miembros máximos por tenant (opcional, para invitaciones)
MAX_MEMBERS: Final[dict[PlanType, int | None]] = {
    PlanType.FREE: 3,
    PlanType.STARTER: 10,
    PlanType.GROWTH: 50,
    PlanType.ENTERPRISE: None,
}

# Servicios máximos por servidor (opcional)
MAX_SERVICES_PER_SERVER: Final[dict[PlanType, int | None]] = {
    PlanType.FREE: 10,
    PlanType.STARTER: 50,
    PlanType.GROWTH: 200,
    PlanType.ENTERPRISE: None,
}

# Jobs máximos por servidor (opcional)
MAX_JOBS_PER_SERVER: Final[dict[PlanType, int | None]] = {
    PlanType.FREE: 5,
    PlanType.STARTER: 20,
    PlanType.GROWTH: 100,
    PlanType.ENTERPRISE: None,
}

# Procesos máximos por servidor (opcional)
MAX_PROCESSES_PER_SERVER: Final[dict[PlanType, int | None]] = {
    PlanType.FREE: 20,
    PlanType.STARTER: 100,
    PlanType.GROWTH: 500,
    PlanType.ENTERPRISE: None,
}


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

class PlanLimitExceededError(Exception):
    """Excepción cuando se excede un límite de plan."""

    def __init__(self, message: str, limit: int | None = None, current: int | None = None) -> None:
        super().__init__(message)
        self.limit = limit
        self.current = current


UNLIMITED: Final = None  # Sentinel para "sin límite"


def get_limit(limit_map: dict[PlanType, int | None], plan: PlanType) -> int | None:
    """Obtiene el límite para un plan, con fallback seguro."""
    return limit_map.get(plan, limit_map[PlanType.FREE])


def is_unlimited(limit: int | None) -> bool:
    """Verifica si un límite es ilimitado (None)."""
    return limit is None


def check_limit(current: int, limit: int | None, resource_name: str) -> None:
    """
    Valida que el uso actual no exceda el límite.

    Args:
        current: Uso actual (contador).
        limit: Límite del plan (None = ilimitado).
        resource_name: Nombre del recurso para el mensaje de error.

    Raises:
        PlanLimitExceededError: Si se excede el límite.
    """
    if limit is None:
        return
    if current >= limit:
        raise PlanLimitExceededError(
            f"Límite de plan alcanzado ({limit} {resource_name}). "
            f"Upgrade tu plan para aumentar el límite."
        )


def get_allowed_channels(plan: PlanType) -> set[str]:
    """Retorna los canales de alerta permitidos para un plan."""
    return ALLOWED_ALERT_CHANNELS.get(plan, ALLOWED_ALERT_CHANNELS[PlanType.FREE])


def validate_alert_channels(plan: PlanType, channels: set[str]) -> None:
    """
    Valida que los canales solicitados estén permitidos para el plan.

    Args:
        plan: Plan del tenant.
        channels: Set de canales solicitados.

    Raises:
        PlanLimitExceededError: Si algún canal no está permitido.
    """
    allowed = get_allowed_channels(plan)
    not_allowed = channels - allowed
    if not_allowed:
        raise PlanLimitExceededError(
            f"Canales de alerta no permitidos en plan {plan.value}: {', '.join(sorted(not_allowed))}. "
            f"Canales permitidos: {', '.join(sorted(allowed))}. "
            f"Upgrade tu plan para acceder a más canales."
        )


def get_retention_days(plan: PlanType) -> int:
    """Retorna los días de retención de métricas para un plan."""
    return METRICS_RETENTION_DAYS.get(plan, METRICS_RETENTION_DAYS[PlanType.FREE])
