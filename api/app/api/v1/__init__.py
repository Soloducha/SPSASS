"""API v1 routers."""

from app.api.v1.alerts import router as alerts_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.ingest import router as ingest_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.processes import router as processes_router
from app.api.v1.servers import router as servers_router
from app.api.v1.services import router as services_router

__all__ = [
    "servers_router",
    "ingest_router",
    "dashboard_router",
    "alerts_router",
    "processes_router",
    "services_router",
    "jobs_router",
]
