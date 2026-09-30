"""Router de procesos: CRUD completo."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.v1.schemas import (
    ProcessCreate,
    ProcessResponse,
    ProcessUpdate,
)
from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.logging import get_logger
from app.repositories.process import ProcessRepository

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/processes", tags=["processes"])


# ──────────────────────────────────────────────
# Process CRUD
# ──────────────────────────────────────────────

@router.get("", response_model=list[ProcessResponse])
async def list_processes(
    session: SessionDep,
    user: CurrentUser,
    server_id: UUID | None = Query(default=None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[ProcessResponse]:
    """Lista procesos del tenant, opcionalmente filtrados por server_id."""
    repo = ProcessRepository(session)
    filters: dict[str, Any] = {}
    if server_id is not None:
        filters["server_id"] = server_id
    processes = await repo.list_all(offset=offset, limit=limit, **filters)
    return [ProcessResponse.model_validate(p) for p in processes]


@router.post("", response_model=ProcessResponse, status_code=status.HTTP_201_CREATED)
async def create_process(
    session: SessionDep,
    user: CurrentUser,
    data: ProcessCreate,
    response: Response,
) -> ProcessResponse:
    """Crea un nuevo proceso."""
    repo = ProcessRepository(session)
    process = await repo.create(**data.model_dump())
    logger.info("process_created", process_id=str(process.id), tenant_id=str(user.tenant_id))
    return ProcessResponse.model_validate(process)


@router.get("/{process_id}", response_model=ProcessResponse)
async def get_process(
    session: SessionDep,
    user: CurrentUser,
    process_id: UUID,
) -> ProcessResponse:
    """Obtiene un proceso por ID."""
    repo = ProcessRepository(session)
    process = await repo.get(process_id)
    if not process:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proceso no encontrado",
        )
    return ProcessResponse.model_validate(process)


@router.patch("/{process_id}", response_model=ProcessResponse)
async def update_process(
    session: SessionDep,
    user: CurrentUser,
    process_id: UUID,
    data: ProcessUpdate,
) -> ProcessResponse:
    """Actualiza un proceso (campos parciales)."""
    repo = ProcessRepository(session)
    process = await repo.update(process_id, **data.model_dump(exclude_unset=True))
    if not process:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proceso no encontrado",
        )
    logger.info("process_updated", process_id=str(process_id), tenant_id=str(user.tenant_id))
    return ProcessResponse.model_validate(process)


@router.delete("/{process_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_process(
    session: SessionDep,
    user: CurrentUser,
    process_id: UUID,
    response: Response,
) -> None:
    """Elimina un proceso."""
    repo = ProcessRepository(session)
    deleted = await repo.delete(process_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proceso no encontrado",
        )
    logger.info("process_deleted", process_id=str(process_id), tenant_id=str(user.tenant_id))
    response.status_code = status.HTTP_204_NO_CONTENT
