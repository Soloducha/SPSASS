"""Router del dashboard: estado general + servidores con últimas métricas."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import and_, func, select

from app.core.auth.dependencies import CurrentUser, SessionDep
from app.models.metric import Metric
from app.models.server import ServerStatus
from app.repositories.server import ServerRepository

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


# ──────────────────────────────────────────────
# Schemas del dashboard
# ──────────────────────────────────────────────
class DashboardTotals(BaseModel):
    """Totales de servidores por estado."""

    total: int
    online: int
    offline: int
    degraded: int
    unknown: int


class ServerOverviewItem(BaseModel):
    """Servidor con sus últimas métricas para el dashboard."""

    id: UUID
    hostname: str
    ip: str | None
    os: str | None
    status: str
    last_heartbeat_at: datetime | None
    latest_metrics: dict[str, float]


class DashboardOverview(BaseModel):
    """Vista general del tenant."""

    totals: DashboardTotals
    servers: list[ServerOverviewItem]


# ──────────────────────────────────────────────
# Endpoint
# ──────────────────────────────────────────────
@router.get("/overview", response_model=DashboardOverview)
async def overview(session: SessionDep, user: CurrentUser) -> DashboardOverview:
    """
    Estado general + servidores del tenant con sus últimas métricas.

    Las últimas métricas se leen de RAW (MAX(ts) por server+tipo): el
    dashboard v0.1 no depende de que el worker haya corrido. El histórico
    (gráficos) usará rollups en una iteración futura.
    """
    repo = ServerRepository(session)
    servers = await repo.list_all()

    # Última observación por (server_id, type) vía MAX(ts) + join (portable)
    latest_ts = (
        select(
            Metric.server_id,
            Metric.type,
            func.max(Metric.ts).label("max_ts"),
        )
        .where(Metric.tenant_id == user.tenant_id)
        .group_by(Metric.server_id, Metric.type)
        .subquery()
    )
    latest_rows = (
        await session.execute(
            select(Metric.server_id, Metric.type, Metric.value).join(
                latest_ts,
                and_(
                    Metric.server_id == latest_ts.c.server_id,
                    Metric.type == latest_ts.c.type,
                    Metric.ts == latest_ts.c.max_ts,
                ),
            )
        )
    ).all()

    latest_by_server: dict[UUID, dict[str, float]] = {}
    for server_id, mtype, value in latest_rows:
        latest_by_server.setdefault(server_id, {})[mtype.value] = value

    counters = {
        ServerStatus.ONLINE: 0,
        ServerStatus.OFFLINE: 0,
        ServerStatus.DEGRADED: 0,
        ServerStatus.UNKNOWN: 0,
    }
    for server in servers:
        counters[server.status] += 1

    return DashboardOverview(
        totals=DashboardTotals(
            total=len(servers),
            online=counters[ServerStatus.ONLINE],
            offline=counters[ServerStatus.OFFLINE],
            degraded=counters[ServerStatus.DEGRADED],
            unknown=counters[ServerStatus.UNKNOWN],
        ),
        servers=[
            ServerOverviewItem(
                id=server.id,
                hostname=server.hostname,
                ip=server.ip,
                os=server.os,
                status=server.status.value,
                last_heartbeat_at=server.last_heartbeat_at,
                latest_metrics=latest_by_server.get(server.id, {}),
            )
            for server in servers
        ],
    )
