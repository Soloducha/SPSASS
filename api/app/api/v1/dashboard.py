"""Router del dashboard: estado general + servidores con ultimas metricas."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, select

from app.core.auth.dependencies import CurrentUser, SessionDep
from app.models.metric import Metric, MetricType
from app.models.metric_rollup import MetricRollup, RollupPeriod
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
    """Servidor con sus ultimas metricas para el dashboard."""

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
# Schemas para historico de metricas
# ──────────────────────────────────────────────

class MetricHistoryPoint(BaseModel):
    """Punto de serie temporal agregado (rollup)."""

    bucket_start: datetime
    avg: float
    min: float
    max: float
    last: float
    count: int


class MetricHistoryResponse(BaseModel):
    """Response para historico de metricas."""

    server_id: UUID
    type: str
    period: str
    points: list[MetricHistoryPoint]


# ──────────────────────────────────────────────
# Endpoint
# ──────────────────────────────────────────────

@router.get("/overview", response_model=DashboardOverview)
async def overview(session: SessionDep, user: CurrentUser) -> DashboardOverview:
    """
    Estado general + servidores del tenant con sus ultimas metricas.

    Las ultimas metricas se leen de RAW (MAX(ts) por server+tipo): el
    dashboard v0.1 no depende de que el worker haya corrido. El historico
    (graficos) usara rollups en una iteracion futura.
    """
    repo = ServerRepository(session)
    servers = await repo.list_all()

    # Ultima observacion por (server_id, type) via MAX(ts) + join (portable)
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


# ──────────────────────────────────────────────
# Endpoint historico de metricas
# ──────────────────────────────────────────────

@router.get("/metrics/history", response_model=MetricHistoryResponse)
async def metrics_history(  # noqa: PLR0913, PLR0917
    session: SessionDep,
    user: CurrentUser,
    server_id: UUID = Query(..., description="ID del servidor"),
    type: str = Query(..., description="Tipo de metrica (cpu_usage, mem_usage, disk_usage, load_avg1, load_avg5, load_avg15)"),
    period: str = Query("5m", description="Periodo de rollup: 1m, 5m, 1h, 1d"),
    from_ts: datetime = Query(..., description="Inicio del periodo (ISO 8601)"),
    to_ts: datetime = Query(..., description="Fin del periodo (ISO 8601)"),
    max_points: int = Query(500, ge=1, le=5000, description="Maximo de puntos a devolver (downsampling si excede)"),
) -> MetricHistoryResponse:
    """
    Historico de metricas desde rollups pre-agregados.

    Usa MetricRollup (1m/5m/1h/1d) para rendimiento. Si los puntos
    exceden max_points, hace downsampling simple (toma cada N-esimo punto).
    """
    # Validar periodo
    try:
        rollup_period = RollupPeriod(period)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Periodo invalido: {period}. Valores validos: 1m, 5m, 1h, 1d",
        ) from e

    # Validar tipo de metrica
    try:
        metric_type = MetricType(type)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Tipo de metrica invalido: {type}",
        ) from e

    # Normalizar fechas a UTC
    def _ensure_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    from_ts_utc = _ensure_utc(from_ts)
    to_ts_utc = _ensure_utc(to_ts)

    # Query rollups
    stmt = select(MetricRollup).where(
        MetricRollup.tenant_id == user.tenant_id,
        MetricRollup.server_id == server_id,
        MetricRollup.type == metric_type,
        MetricRollup.period == rollup_period,
        MetricRollup.bucket_start >= from_ts_utc,
        MetricRollup.bucket_start <= to_ts_utc,
    ).order_by(MetricRollup.bucket_start)

    result = await session.execute(stmt)
    rollups = list(result.scalars().all())

    points = [
        MetricHistoryPoint(
            bucket_start=r.bucket_start,
            avg=r.avg,
            min=r.min,
            max=r.max,
            last=r.last,
            count=r.count,
        )
        for r in rollups
    ]

    # Downsampling si excede max_points
    if len(points) > max_points:
        step = len(points) // max_points + 1
        points = points[::step]

    return MetricHistoryResponse(
        server_id=server_id,
        type=metric_type.value,
        period=rollup_period.value,
        points=points,
    )
