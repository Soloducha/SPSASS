"""Router de servicios: CRUD completo."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.v1.schemas import (
    ServiceCreate,
    ServiceResponse,
    ServiceUpdate,
)
from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.logging import get_logger
from app.repositories.service import ServiceRepository

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/services", tags=["services"])


# ──────────────────────────────────────────────
# Service CRUD
# ──────────────────────────────────────────────

@router.get("", response_model=list[ServiceResponse])
async def list_services(
    session: SessionDep,
    user: CurrentUser,
    server_id: UUID | None = Query(default=None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[ServiceResponse]:
    """Lista servicios del tenant, opcionalmente filtrados por server_id."""
    repo = ServiceRepository(session)
    filters: dict[str, Any] = {}
    if server_id is not None:
        filters["server_id"] = server_id
    services = await repo.list_all(offset=offset, limit=limit, **filters)
    return [ServiceResponse.model_validate(s) for s in services]


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_service(
    session: SessionDep,
    user: CurrentUser,
    data: ServiceCreate,
    response: Response,
) -> ServiceResponse:
    """Crea un nuevo servicio."""
    repo = ServiceRepository(session)
    service = await repo.create(**data.model_dump())
    logger.info("service_created", service_id=str(service.id), tenant_id=str(user.tenant_id))
    return ServiceResponse.model_validate(service)


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_service(
    session: SessionDep,
    user: CurrentUser,
    service_id: UUID,
) -> ServiceResponse:
    """Obtiene un servicio por ID."""
    repo = ServiceRepository(session)
    service = await repo.get(service_id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Servicio no encontrado",
        )
    return ServiceResponse.model_validate(service)


@router.patch("/{service_id}", response_model=ServiceResponse)
async def update_service(
    session: SessionDep,
    user: CurrentUser,
    service_id: UUID,
    data: ServiceUpdate,
) -> ServiceResponse:
    """Actualiza un servicio (campos parciales)."""
    repo = ServiceRepository(session)
    service = await repo.update(service_id, **data.model_dump(exclude_unset=True))
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Servicio no encontrado",
        )
    logger.info("service_updated", service_id=str(service_id), tenant_id=str(user.tenant_id))
    return ServiceResponse.model_validate(service)


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    session: SessionDep,
    user: CurrentUser,
    service_id: UUID,
    response: Response,
) -> None:
    """Elimina un servicio."""
    repo = ServiceRepository(session)
    deleted = await repo.delete(service_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Servicio no encontrado",
        )
    logger.info("service_deleted", service_id=str(service_id), tenant_id=str(user.tenant_id))
    response.status_code = status.HTTP_204_NO_CONTENT
