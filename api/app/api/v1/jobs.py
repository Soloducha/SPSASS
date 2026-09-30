"""Router de jobs: CRUD completo + historial de ejecuciones (JobRun)."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.v1.schemas import (
    JobCreate,
    JobListParams,
    JobResponse,
    JobRunListParams,
    JobRunResponse,
    JobUpdate,
)
from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.logging import get_logger
from app.repositories.job import JobRepository, JobRunRepository

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


# ──────────────────────────────────────────────
# Job CRUD
# ──────────────────────────────────────────────

@router.get("", response_model=list[JobResponse])
async def list_jobs(
    session: SessionDep,
    user: CurrentUser,
    params: JobListParams = Query(),
) -> list[JobResponse]:
    """Lista jobs del tenant, opcionalmente filtrados por server_id y/o status."""
    repo = JobRepository(session)
    filters: dict[str, Any] = {}
    if params.server_id is not None:
        filters["server_id"] = params.server_id
    if params.status is not None:
        filters["status"] = params.status
    jobs = await repo.list_all(offset=params.offset, limit=params.limit, **filters)
    return [JobResponse.model_validate(j) for j in jobs]


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    session: SessionDep,
    user: CurrentUser,
    data: JobCreate,
    response: Response,
) -> JobResponse:
    """Crea un nuevo job."""
    repo = JobRepository(session)
    job = await repo.create(**data.model_dump())
    logger.info("job_created", job_id=str(job.id), tenant_id=str(user.tenant_id))
    return JobResponse.model_validate(job)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    session: SessionDep,
    user: CurrentUser,
    job_id: UUID,
) -> JobResponse:
    """Obtiene un job por ID."""
    repo = JobRepository(session)
    job = await repo.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job no encontrado",
        )
    return JobResponse.model_validate(job)


@router.patch("/{job_id}", response_model=JobResponse)
async def update_job(
    session: SessionDep,
    user: CurrentUser,
    job_id: UUID,
    data: JobUpdate,
) -> JobResponse:
    """Actualiza un job (campos parciales)."""
    repo = JobRepository(session)
    job = await repo.update(job_id, **data.model_dump(exclude_unset=True))
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job no encontrado",
        )
    logger.info("job_updated", job_id=str(job_id), tenant_id=str(user.tenant_id))
    return JobResponse.model_validate(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    session: SessionDep,
    user: CurrentUser,
    job_id: UUID,
    response: Response,
) -> None:
    """Elimina un job (cascada elimina sus JobRuns)."""
    repo = JobRepository(session)
    deleted = await repo.delete(job_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job no encontrado",
        )
    logger.info("job_deleted", job_id=str(job_id), tenant_id=str(user.tenant_id))
    response.status_code = status.HTTP_204_NO_CONTENT


# ──────────────────────────────────────────────
# JobRun History (read-only para T1)
# ──────────────────────────────────────────────

@router.get("/{job_id}/runs", response_model=list[JobRunResponse])
async def list_job_runs(
    session: SessionDep,
    user: CurrentUser,
    job_id: UUID,
    params: JobRunListParams = Query(),
) -> list[JobRunResponse]:
    """Lista ejecuciones de un job (tenant-scoped + job_id scoped), más recientes primero."""
    # Primero verificar que el job existe y pertenece al tenant
    job_repo = JobRepository(session)
    job = await job_repo.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job no encontrado",
        )

    run_repo = JobRunRepository(session)
    runs = await run_repo.list_by_job(job_id, offset=params.offset, limit=params.limit)
    return [JobRunResponse.model_validate(r) for r in runs]
