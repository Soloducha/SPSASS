"""API routers."""

from app.api.v1 import dashboard_router, ingest_router, servers_router
from app.core.auth.router import router as auth_router

__all__ = ["auth_router", "servers_router", "ingest_router", "dashboard_router"]
