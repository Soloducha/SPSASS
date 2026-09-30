"""Repositorios para jobs y job runs con scoping de tenant."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, desc, func, select
from sqlalchemy.orm import InstrumentedAttribute

from app.models.job import Job, JobRun, JobStatus
from app.repositories.base import TenantScopedRepository


class JobRepository(TenantScopedRepository):
    """Repositorio concreto para Job."""

    model = Job

    async def list_all(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: InstrumentedAttribute[Any] | None = None,
        **filters: object,
    ) -> Sequence[Job]:
        """Lista jobs con paginación y filtros opcionales + tenant."""
        # Si no se especifica order_by, usar created_at descendente por defecto
        if order_by is None:
            stmt = self._base_select().filter_by(**filters).order_by(Job.created_at.desc())
            stmt = stmt.offset(offset).limit(limit)
            result = await self.session.execute(stmt)
            return result.scalars().all()
        return await super().list_all(offset=offset, limit=limit, order_by=order_by, **filters)

    async def list_by_server(self, server_id: UUID, *, offset: int = 0, limit: int = 100) -> Sequence[Job]:
        """Lista jobs de un servidor específico (tenant-scoped), más recientes primero."""
        stmt = self._base_select().filter_by(server_id=server_id).order_by(Job.created_at.desc())
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_status(self, status: JobStatus, *, offset: int = 0, limit: int = 100) -> Sequence[Job]:
        """Lista jobs por estado (tenant-scoped), más recientes primero."""
        stmt = self._base_select().filter_by(status=status).order_by(Job.created_at.desc())
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()


class JobRunRepository(TenantScopedRepository):
    """Repositorio para JobRun con scoping por tenant Y job_id."""

    model = JobRun

    async def list_by_job(
        self,
        job_id: UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[JobRun]:
        """Lista ejecuciones de un job específico (tenant + job_id scoped), más recientes primero."""
        stmt: Select = (
            self._base_select()
            .where(JobRun.job_id == job_id)
            .order_by(desc(JobRun.started_at))
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_by_job(self, job_id: UUID) -> int:
        """Cuenta ejecuciones de un job específico (tenant + job_id scoped)."""
        stmt = select(func.count()).select_from(JobRun).where(
            JobRun.tenant_id == self._tenant_id,
            JobRun.job_id == job_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_latest_by_job(self, job_id: UUID) -> JobRun | None:
        """Obtiene la última ejecución de un job (tenant + job_id scoped)."""
        stmt = (
            self._base_select()
            .where(JobRun.job_id == job_id)
            .order_by(desc(JobRun.started_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_run(
        self,
        job_id: UUID,
        *,
        started_at: datetime | None = None,
        status: str = "running",
        run_metadata: dict | None = None,
    ) -> JobRun:
        """Crea una nueva ejecución de job (para uso del runner T2)."""
        if started_at is None:
            started_at = datetime.now(UTC)
        data: dict[str, Any] = {
            "job_id": job_id,
            "started_at": started_at,
            "status": status,
            "run_metadata": run_metadata or {},
        }
        return await self.create(**data)  # type: ignore[no-any-return]

    async def finish_run(
        self,
        run_id: UUID,
        *,
        finished_at: datetime | None = None,
        exit_code: int | None = None,
        status: str = "success",
        updates: dict[str, Any] | None = None,
    ) -> JobRun | None:
        """Finaliza una ejecución de job (para uso del runner T2)."""
        if finished_at is None:
            finished_at = datetime.now(UTC)
        run = await self.get(run_id)
        if not run:
            return None
        update_data: dict[str, Any] = {"finished_at": finished_at, "exit_code": exit_code, "status": status}
        if updates:
            update_data.update(updates)
        return await self.update(run_id, **update_data)  # type: ignore[no-any-return]
