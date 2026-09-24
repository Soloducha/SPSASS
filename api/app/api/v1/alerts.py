"""Router de alertas: CRUD de reglas y ciclo de vida de alertas (T3 + T4)."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.v1.schemas import (
    AlertAckRequest,
    AlertAckResponse,
    AlertListParams,
    AlertResponse,
    AlertRuleCreate,
    AlertRuleResponse,
    AlertRuleUpdate,
)
from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.logging import get_logger
from app.repositories.alert import AlertRepository, AlertRuleRepository

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


# ──────────────────────────────────────────────
# Alert Rule CRUD (T3)
# ──────────────────────────────────────────────

@router.get("/rules", response_model=list[AlertRuleResponse])
async def list_alert_rules(
    session: SessionDep,
    user: CurrentUser,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[AlertRuleResponse]:
    """Lista reglas de alerta del tenant."""
    repo = AlertRuleRepository(session)
    rules = await repo.list_all(offset=offset, limit=limit)
    return [AlertRuleResponse.model_validate(rule) for rule in rules]


@router.post("/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    session: SessionDep,
    user: CurrentUser,
    data: AlertRuleCreate,
    response: Response,
) -> AlertRuleResponse:
    """Crea una nueva regla de alerta."""
    repo = AlertRuleRepository(session)
    rule = await repo.create(**data.model_dump())
    logger.info("alert_rule_created", rule_id=str(rule.id), tenant_id=str(user.tenant_id))
    return AlertRuleResponse.model_validate(rule)


@router.get("/rules/{rule_id}", response_model=AlertRuleResponse)
async def get_alert_rule(
    session: SessionDep,
    user: CurrentUser,
    rule_id: UUID,
) -> AlertRuleResponse:
    """Obtiene una regla de alerta por ID."""
    repo = AlertRuleRepository(session)
    rule = await repo.get(rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert rule no encontrada",
        )
    return AlertRuleResponse.model_validate(rule)


@router.patch("/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    session: SessionDep,
    user: CurrentUser,
    rule_id: UUID,
    data: AlertRuleUpdate,
) -> AlertRuleResponse:
    """Actualiza una regla de alerta (campos parciales)."""
    repo = AlertRuleRepository(session)
    rule = await repo.update(rule_id, **data.model_dump(exclude_unset=True))
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert rule no encontrada",
        )
    logger.info("alert_rule_updated", rule_id=str(rule_id), tenant_id=str(user.tenant_id))
    return AlertRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    session: SessionDep,
    user: CurrentUser,
    rule_id: UUID,
    response: Response,
) -> None:
    """Elimina una regla de alerta."""
    repo = AlertRuleRepository(session)
    deleted = await repo.delete(rule_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert rule no encontrada",
        )
    logger.info("alert_rule_deleted", rule_id=str(rule_id), tenant_id=str(user.tenant_id))
    response.status_code = status.HTTP_204_NO_CONTENT


# ──────────────────────────────────────────────
# Alert Lifecycle (T4)
# ──────────────────────────────────────────────

@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    session: SessionDep,
    user: CurrentUser,
    params: AlertListParams = Query(),
) -> list[AlertResponse]:
    """Lista alertas del tenant con filtros opcionales."""
    repo = AlertRepository(session)
    alerts = await repo.list_filtered(
        status=params.status,
        severity=params.severity,
        rule_id=params.rule_id,
        offset=params.offset,
        limit=params.limit,
    )
    return [AlertResponse.model_validate(alert) for alert in alerts]


@router.post("/{alert_id}/ack", response_model=AlertAckResponse)
async def acknowledge_alert(
    session: SessionDep,
    user: CurrentUser,
    alert_id: UUID,
    data: AlertAckRequest,
) -> AlertAckResponse:
    """Marca una alerta como acknowledged."""
    repo = AlertRepository(session)
    alert = await repo.acknowledge(alert_id, data.acknowledged_by)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alerta no encontrada",
        )
    logger.info(
        "alert_acknowledged",
        alert_id=str(alert_id),
        tenant_id=str(user.tenant_id),
        acknowledged_by=str(data.acknowledged_by),
    )
    return AlertAckResponse(
        id=alert.id,
        status=alert.status,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
        acknowledged_by=alert.acknowledged_by,
    )


@router.post("/{alert_id}/resolve", response_model=AlertAckResponse)
async def resolve_alert(
    session: SessionDep,
    user: CurrentUser,
    alert_id: UUID,
) -> AlertAckResponse:
    """Marca una alerta como resolved."""
    repo = AlertRepository(session)
    alert = await repo.resolve(alert_id)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alerta no encontrada",
        )
    logger.info(
        "alert_resolved",
        alert_id=str(alert_id),
        tenant_id=str(user.tenant_id),
    )
    return AlertAckResponse(
        id=alert.id,
        status=alert.status,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
        acknowledged_by=alert.acknowledged_by,
    )
