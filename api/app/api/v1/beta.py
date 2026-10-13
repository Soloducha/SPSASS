"""API endpoints para Beta Cerrada (T5 - Mes 6).

Endpoints admin:
- POST   /api/v1/beta/pilots              - Agregar piloto
- GET    /api/v1/beta/pilots              - Listar pilotos
- GET    /api/v1/beta/pilots/{tenant_id}  - Obtener piloto
- PATCH  /api/v1/beta/pilots/{tenant_id}  - Actualizar estado piloto
- DELETE /api/v1/beta/pilots/{tenant_id}  - Remover piloto

Endpoints piloto (feedback):
- POST   /api/v1/beta/feedback            - Enviar feedback
- GET    /api/v1/beta/feedback            - Listar feedback (admin)

Endpoints métricas (admin):
- GET    /api/v1/beta/metrics/summary     - Resumen agregado
- GET    /api/v1/beta/metrics/pilot/{tenant_id} - Métricas de un piloto
- GET    /api/v1/beta/metrics/all         - Métricas de todos los pilotos

Endpoints públicos (widget):
- GET    /api/v1/beta/status              - Verifica si beta habilitada
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.schemas import (
    BetaFeedbackCreate,
    BetaFeedbackResponse,
    BetaMetricsSummaryResponse,
    BetaPilotCreate,
    BetaPilotResponse,
    BetaPilotStatusUpdate,
    BetaStatusResponse,
    PilotMetricsSnapshotResponse,
)
from app.core.auth.dependencies import CurrentUser, RequireAdmin, SessionDep
from app.core.beta import BetaService, PilotStatus, PilotMetricsSnapshot, get_beta_service
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/beta", tags=["beta"])


# ──────────────────────────────────────────────
# Public: Beta Status
# ──────────────────────────────────────────────

@router.get("/status", response_model=BetaStatusResponse)
async def get_beta_status() -> BetaStatusResponse:
    """
    Verifica si la beta cerrada está habilitada.
    Endpoint público para que el frontend sepa si mostrar widget de feedback, etc.
    """
    service = BetaService(None)  # type: ignore[arg-type]
    return BetaStatusResponse(
        beta_enabled=service.is_beta_enabled(),
        feedback_enabled=service.is_feedback_enabled(),
        metrics_enabled=service.is_metrics_enabled(),
    )


# ──────────────────────────────────────────────
# Admin: Pilot Management
# ──────────────────────────────────────────────

@router.post("/pilots", response_model=BetaPilotResponse, status_code=status.HTTP_201_CREATED)
async def create_pilot(
    user: RequireAdmin,
    data: BetaPilotCreate,
    session: SessionDep,
    beta_service: BetaService = Depends(get_beta_service),
) -> BetaPilotResponse:
    """
    Agrega un tenant como piloto de la beta cerrada.
    Requiere rol ADMIN u OWNER.
    """
    if not beta_service.is_beta_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Beta cerrada no está habilitada (BETA_ENABLED=false)",
        )
    
    try:
        pilot = await beta_service.add_pilot(
            tenant_id=data.tenant_id,
            invited_by_id=user.id,
            notes=data.notes if hasattr(data, "notes") else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    
    return BetaPilotResponse.model_validate(pilot)


@router.get("/pilots", response_model=list[BetaPilotResponse])
async def list_pilots(
    user: RequireAdmin,
    session: SessionDep,
    beta_service: BetaService = Depends(get_beta_service),
    status: Optional[PilotStatus] = Query(None, description="Filtrar por estado"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[BetaPilotResponse]:
    """Lista pilotos de la beta (admin)."""
    pilots = await beta_service.list_pilots(status=status, offset=offset, limit=limit)
    return [BetaPilotResponse.model_validate(p) for p in pilots]


@router.get("/pilots/{tenant_id}", response_model=BetaPilotResponse)
async def get_pilot(
    user: RequireAdmin,
    tenant_id: UUID,
    session: SessionDep,
    beta_service: BetaService = Depends(get_beta_service),
) -> BetaPilotResponse:
    """Obtiene info de un piloto específico (admin)."""
    pilot = await beta_service.get_pilot(tenant_id)
    if not pilot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Piloto no encontrado",
        )
    return BetaPilotResponse.model_validate(pilot)


@router.patch("/pilots/{tenant_id}", response_model=BetaPilotResponse)
async def update_pilot_status(
    user: RequireAdmin,
    tenant_id: UUID,
    data: BetaPilotStatusUpdate,
    session: SessionDep,
    beta_service: BetaService = Depends(get_beta_service),
) -> BetaPilotResponse:
    """Actualiza estado de un piloto (onboard, complete, remove, etc.)."""
    pilot = await beta_service.get_pilot(tenant_id)
    if not pilot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Piloto no encontrado",
        )
    
    # Aplicar transición de estado según action
    action = data.action
    if action == "onboard":
        pilot = await beta_service.onboard_pilot(tenant_id)
    elif action == "complete":
        pilot = await beta_service.complete_pilot(tenant_id)
    elif action == "remove":
        await beta_service.remove_pilot(tenant_id)
        pilot = await beta_service.get_pilot(tenant_id)
    elif action == "reactivate":
        # Reactivar piloto removido/inactivo
        pilot.status = PilotStatus.ACTIVE
        pilot.onboarded_at = datetime.now(UTC)
        await session.flush()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Acción inválida: {action}. Permitidas: onboard, complete, remove, reactivate",
        )
    
    if not pilot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Piloto no encontrado después de actualizar",
        )
    
    return BetaPilotResponse.model_validate(pilot)


@router.delete("/pilots/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pilot(
    user: RequireAdmin,
    tenant_id: UUID,
    session: SessionDep,
    beta_service: BetaService = Depends(get_beta_service),
) -> None:
    """Remueve un piloto de la beta (soft delete: status=REMOVED)."""
    removed = await beta_service.remove_pilot(tenant_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Piloto no encontrado",
        )


# ──────────────────────────────────────────────
# Feedback (Piloto + Admin)
# ──────────────────────────────────────────────

@router.post("/feedback", response_model=BetaFeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    user: CurrentUser,
    data: BetaFeedbackCreate,
    session: SessionDep,
    beta_service: BetaService = Depends(get_beta_service),
) -> BetaFeedbackResponse:
    """
    Envía feedback desde el widget in-app.
    Requiere que el usuario pertenezca a un tenant piloto activo.
    """
    if not beta_service.is_feedback_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Feedback widget no está habilitado",
        )
    
    # Verificar que el tenant del usuario es piloto activo
    is_pilot = await beta_service.is_tenant_pilot(user.tenant_id)
    if not is_pilot:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu tenant no participa en la beta cerrada",
        )
    
    # Obtener pilot_id
    pilot = await beta_service.get_pilot(user.tenant_id)
    if not pilot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Piloto no encontrado",
        )
    
    feedback = await beta_service.submit_feedback(
        pilot_id=pilot.id,
        category=data.category,
        title=data.title,
        description=data.description,
        user_id=user.id,
        user_email=user.email,
        rating=data.rating,
        page_url=data.page_url,
        user_agent=data.user_agent,
        screen_resolution=data.screen_resolution,
    )
    
    return BetaFeedbackResponse.model_validate(feedback)


@router.get("/feedback", response_model=list[BetaFeedbackResponse])
async def list_feedback(
    user: RequireAdmin,
    session: SessionDep,
    beta_service: BetaService = Depends(get_beta_service),
    pilot_id: Optional[UUID] = Query(None, description="Filtrar por piloto"),
    status: Optional[str] = Query(None, description="Filtrar por estado (new, triaged, in_progress, done, wont_fix)"),
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[BetaFeedbackResponse]:
    """Lista feedback de pilotos (admin)."""
    feedback_list = await beta_service.list_feedback(
        pilot_id=pilot_id,
        status=status,
        category=category,
        offset=offset,
        limit=limit,
    )
    return [BetaFeedbackResponse.model_validate(f) for f in feedback_list]


# ──────────────────────────────────────────────
# Métricas (Admin)
# ──────────────────────────────────────────────

@router.get("/metrics/summary", response_model=BetaMetricsSummaryResponse)
async def get_metrics_summary(
    user: RequireAdmin,
    session: SessionDep,
    beta_service: BetaService = Depends(get_beta_service),
    days: int = Query(30, ge=1, le=365, description="Días hacia atrás para agregación"),
) -> BetaMetricsSummaryResponse:
    """Resumen agregado de métricas de adopción de todos los pilotos activos."""
    if not beta_service.is_metrics_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Métricas de adopción no habilitadas",
        )
    
    metrics = await beta_service.get_aggregated_metrics(days=days)
    return BetaMetricsSummaryResponse(**metrics)


@router.get("/metrics/pilot/{tenant_id}", response_model=list[PilotMetricsSnapshotResponse])
async def get_pilot_metrics(
    user: RequireAdmin,
    tenant_id: UUID,
    session: SessionDep,
    beta_service: BetaService = Depends(get_beta_service),
    days: int = Query(30, ge=1, le=365),
) -> list[PilotMetricsSnapshotResponse]:
    """Métricas diarias de un piloto específico."""
    pilot = await beta_service.get_pilot(tenant_id)
    if not pilot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Piloto no encontrado",
        )
    
    end_date = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=days)
    
    metrics = await beta_service.get_metrics_range(pilot.id, start_date, end_date)
    return [PilotMetricsSnapshotResponse.model_validate(m) for m in metrics]


@router.get("/metrics/all", response_model=list[BetaMetricsSummaryResponse])
async def get_all_pilots_metrics(
    user: RequireAdmin,
    session: SessionDep,
    beta_service: BetaService = Depends(get_beta_service),
    days: int = Query(30, ge=1, le=365),
) -> list[BetaMetricsSummaryResponse]:
    """Métricas agregadas por piloto (para tabla comparativa)."""
    pilots = await beta_service.list_pilots(status=PilotStatus.ACTIVE)
    
    results = []
    for pilot in pilots:
        metrics = await beta_service.get_aggregated_metrics(pilot_id=pilot.id, days=days)
        metrics["pilot_tenant_id"] = str(pilot.tenant_id)
        metrics["pilot_status"] = pilot.status.value
        results.append(BetaMetricsSummaryResponse(**metrics))
    
    return results