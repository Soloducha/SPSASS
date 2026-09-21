"""Contexto de tenant para aislamiento multi-tenant (RLS + query scoping).

Usa contextvars para almacenar el tenant_id por request (async-safe).
Este contexto se inyecta en PostgreSQL via `SET LOCAL app.tenant_id = '...'`
para que las políticas RLS funcionen.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

from app.core.logging import get_logger

logger = get_logger(__name__)

# ContextVar para tenant_id actual (async-safe, aislado por request)
_tenant_id_var: ContextVar[UUID | None] = ContextVar("tenant_id", default=None)
# ContextVar para indicar si el contexto fue seteado explícitamente (vs heredado)
_tenant_set_var: ContextVar[bool] = ContextVar("tenant_set", default=False)


class TenantContext:
    """Contenedor de información del tenant actual en el request."""

    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id

    def __repr__(self) -> str:
        return f"TenantContext(tenant_id={self.tenant_id})"


def get_tenant_context() -> TenantContext | None:
    """Obtiene el contexto de tenant actual (None si no hay)."""
    tenant_id = _tenant_id_var.get()
    if tenant_id is None:
        return None
    return TenantContext(tenant_id)


def set_tenant_context(tenant_id: UUID) -> None:
    """
    Establece el tenant_id en el contexto actual.
    Debe llamarse al inicio del request (middleware o dependency).
    """
    _tenant_id_var.set(tenant_id)
    _tenant_set_var.set(True)
    logger.debug("tenant_context_set", tenant_id=str(tenant_id))


def clear_tenant_context() -> None:
    """Limpia el contexto de tenant (al final del request)."""
    _tenant_id_var.set(None)
    _tenant_set_var.set(False)
    logger.debug("tenant_context_cleared")


def require_tenant_context() -> UUID:
    """
    Obtiene el tenant_id obligatorio; lanza error si no hay contexto.
    Útil en repositorios/queries que requieren tenant obligatoriamente.
    """
    tenant_id = _tenant_id_var.get()
    if tenant_id is None:
        raise RuntimeError(
            "Tenant context not set. Ensure TenantMiddleware runs or "
            "set_tenant_context() is called before querying."
        )
    return tenant_id


def is_tenant_context_set() -> bool:
    """Verifica si hay un tenant_id seteado en el contexto actual."""
    return _tenant_set_var.get()


@contextmanager
def tenant_context(tenant_id: UUID):
    """
    Context manager para setear tenant temporalmente.
    Útil en tests, workers, o código que necesita cambiar de tenant.
    """
    previous_id = _tenant_id_var.get()
    previous_set = _tenant_set_var.get()
    try:
        set_tenant_context(tenant_id)
        yield
    finally:
        if previous_set:
            _tenant_id_var.set(previous_id)
            _tenant_set_var.set(True)
        else:
            clear_tenant_context()