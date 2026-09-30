"""API routers."""

from app.api.v1 import (
    alerts_router,
    dashboard_router,
    ingest_router,
    jobs_router,
    processes_router,
    servers_router,
    services_router,
)
from app.core.auth.router import router as auth_router

__all__ = [
    "auth_router",
    "servers_router",
    "ingest_router",
    "dashboard_router",
    "alerts_router",
    "processes_router",
    "services_router",
    "jobs_router",
]
