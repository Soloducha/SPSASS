"""Router de reportes: CRUD completo + generación asíncrona."""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.v1.schemas import (
    ReportCreate,
    ReportGenerateRequest,
    ReportListResponse,
    ReportResponse,
)
from app.core.auth.dependencies import CurrentTenant, CurrentUser, SessionDep
from app.core.logging import get_logger
from app.core.plan import guard_report_creation
from app.models.report import ReportStatus, ReportType
from app.repositories.report import ReportRepository

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _map_query_to_filters(
    type: ReportType | None = None,
    status: ReportStatus | None = None,
    period_start: str | None = None,
    period_end: str | None = None,
) -> dict[str, Any]:
    """Mapea parámetros de query a filtros del repositorio."""
    filters: dict[str, Any] = {}
    if type is not None:
        filters["type"] = type
    if status is not None:
        filters["status"] = status
    # period_start/end se manejan por separado en list_filtered
    return filters


def _parse_datetime(value: str | None) -> datetime | None:
    """Parsea string ISO a datetime (FastAPI ya valida, esto es por si acaso)."""
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ──────────────────────────────────────────────
# CRUD Reportes
# ──────────────────────────────────────────────

@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def create_report(
    session: SessionDep,
    tenant: CurrentTenant,
    data: ReportCreate,
    response: Response,
) -> ReportResponse:
    """Crea un reporte manual con status PENDING."""
    # Plan Gate: validar límite de reportes/mes antes de crear
    await guard_report_creation(session, tenant)

    repo = ReportRepository(session)
    report = await repo.create(
        type=data.type,
        period_start=data.period_start,
        period_end=data.period_end,
        payload=data.params,
        status=ReportStatus.PENDING,
    )
    logger.info("report_created", report_id=str(report.id), tenant_id=str(tenant.id), type=data.type.value)
    return ReportResponse.model_validate(report)


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_report(
    session: SessionDep,
    tenant: CurrentTenant,
    data: ReportGenerateRequest,
response: Response,
) -> None:
    """Generación asíncrona de reporte.

    Crea un Report con status=PENDING y devuelve 202 + Location header.
    El worker (T3) procesará el reporte y actualizará status/payload.
    """
    # Plan Gate: validar límite de reportes/mes antes de crear
    await guard_report_creation(session, tenant)

    repo = ReportRepository(session)
    report = await repo.create(
        type=data.type,
        period_start=data.period_start,
        period_end=data.period_end,
        payload=data.params or {},
        status=ReportStatus.PENDING,
    )
    logger.info("report_generate_queued", report_id=str(report.id), tenant_id=str(tenant.id), type=data.type.value)

    # 202 Accepted + Location header
    response.status_code = status.HTTP_202_ACCEPTED
    response.headers["Location"] = f"/api/v1/reports/{report.id}"


@router.get("", response_model=ReportListResponse)
async def list_reports(  # noqa: PLR0913, PLR0917
    session: SessionDep,
    user: CurrentUser,
    type: ReportType | None = Query(None, description="Filtrar por tipo de reporte"),
    status: ReportStatus | None = Query(None, description="Filtrar por estado"),
    period_start: str | None = Query(None, description="Filtrar por período inicio (ISO 8601)"),
    period_end: str | None = Query(None, description="Filtrar por período fin (ISO 8601)"),
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(50, ge=1, le=200, description="Tamaño de página"),
) -> ReportListResponse:
    """Lista reportes del tenant con filtros opcionales."""
    repo = ReportRepository(session)

    offset = (page - 1) * page_size

    # Parsear fechas si vienen
    ps = _parse_datetime(period_start)
    pe = _parse_datetime(period_end)

    reports = await repo.list_filtered(
        type=type,
        status=status,
        period_start=ps,
        period_end=pe,
        offset=offset,
        limit=page_size,
    )

    total = await repo.count_filtered(
        type=type,
        status=status,
        period_start=ps,
        period_end=pe,
    )

    return ReportListResponse(
        items=[ReportResponse.model_validate(r) for r in reports],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    session: SessionDep,
    user: CurrentUser,
    report_id: UUID,
) -> ReportResponse:
    """Obtiene un reporte por ID con payload completo."""
    repo = ReportRepository(session)
    report = await repo.get_with_payload(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reporte no encontrado",
        )
    return ReportResponse.model_validate(report)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    session: SessionDep,
    user: CurrentUser,
    report_id: UUID,
    response: Response,
) -> None:
    """Soft delete: marca el reporte como CANCELLED."""
    repo = ReportRepository(session)
    report = await repo.get(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reporte no encontrado",
        )

    # Soft delete: marcar como CANCELLED
    await repo.update(report_id, status=ReportStatus.CANCELLED)
    logger.info("report_cancelled", report_id=str(report_id), tenant_id=str(user.tenant_id))
    response.status_code = status.HTTP_204_NO_CONTENT
