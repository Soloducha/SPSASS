"""Middleware FastAPI para inyección automática de contexto de tenant.

Inyecta el tenant_id en:
1. ContextVar (para query scoping en repositorios)
2. PostgreSQL session variable `app.tenant_id` (para RLS)
"""
from uuid import UUID

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger
from app.core.tenant.context import clear_tenant_context, set_tenant_context

logger = get_logger(__name__)


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware que extrae tenant_id del request y lo inyecta en el contexto.

    Fuentes de tenant_id (en orden de prioridad):
    1. Header `X-Tenant-ID` (para testing/admin overrides)
    2. Estado del request (`request.state.tenant_id`) seteado por dependencias de auth
    3. JWT token (vía dependency get_current_user -> user.tenant_id)
    4. API Key (vía dependency get_tenant_from_api_key -> tenant.id)

    Nota: Las dependencias de auth (get_current_tenant, get_tenant_from_api_key)
    ya setean `request.state.tenant_id`. Este middleware lo lee y lo propaga
    a ContextVar + PostgreSQL.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Intentar obtener tenant_id del request state (seteado por auth deps)
        tenant_id: UUID | None = getattr(request.state, "tenant_id", None)

        # Fallback: header explícito (solo para testing/admin)
        if tenant_id is None:
            header_tenant = request.headers.get("X-Tenant-ID")
            if header_tenant:
                try:
                    tenant_id = UUID(header_tenant)
                except ValueError:
                    logger.warning("invalid_x_tenant_id_header", value=header_tenant)

        # Si hay tenant_id, inyectar en contexto y PostgreSQL
        if tenant_id is not None:
            set_tenant_context(tenant_id)
            # La variable de sesión PostgreSQL se setea via DB session dependency
            # (ver db/session.py get_db_session_with_tenant)
            logger.debug("tenant_middleware_injected", tenant_id=str(tenant_id))

        try:
            response = await call_next(request)
            return response
        finally:
            # Limpiar contexto al final del request
            clear_tenant_context()