"""API v1 routers."""

from app.api.v1.alerts import router as alerts_router
from app.api.v1.api_keys import router as api_keys_router
from app.api.v1.beta import router as beta_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.ingest import router as ingest_router
from app.api.v1.invitations import router as invitations_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.processes import router as processes_router
from app.api.v1.reports import router as reports_router
from app.api.v1.servers import router as servers_router
from app.api.v1.services import router as services_router

__all__ = [
    "api_keys_router",
    "beta_router",
    "servers_router",
    "ingest_router",
    "dashboard_router",
    "alerts_router",
    "processes_router",
    "services_router",
    "jobs_router",
    "reports_router",
    "invitations_router",
]
