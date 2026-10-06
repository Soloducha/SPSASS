"""Repositorio para reportes con scoping de tenant."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from app.models.report import Report, ReportStatus, ReportType
from app.repositories.base import TenantScopedRepository


class ReportRepository(TenantScopedRepository):
    """Repositorio concreto para Report."""

    model = Report

    async def list_all(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: Any = None,  # noqa: ANN401
        **filters: Any,  # noqa: ANN401
    ) -> Sequence[Report]:
        """Lista reportes con paginación y filtros opcionales + tenant, más recientes primero."""
        if order_by is None:
            stmt = self._base_select().filter_by(**filters).order_by(Report.created_at.desc())
            stmt = stmt.offset(offset).limit(limit)
            result = await self.session.execute(stmt)
            return result.scalars().all()
        return await super().list_all(offset=offset, limit=limit, order_by=order_by, **filters)

    async def list_filtered(self,  # noqa: PLR0913
        *,
        type: ReportType | None = None,
        status: ReportStatus | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Report]:
        """Lista reportes con filtros específicos del dominio."""
        stmt = self._base_select()

        if type is not None:
            stmt = stmt.where(Report.type == type)
        if status is not None:
            stmt = stmt.where(Report.status == status)
        if period_start is not None:
            stmt = stmt.where(Report.period_start >= period_start)
        if period_end is not None:
            stmt = stmt.where(Report.period_end <= period_end)

        stmt = stmt.order_by(Report.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_filtered(
        self,
        *,
        type: ReportType | None = None,
        status: ReportStatus | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> int:
        """Cuenta reportes con filtros específicos del dominio."""
        stmt = select(func.count()).select_from(Report).where(Report.tenant_id == self._tenant_id)

        if type is not None:
            stmt = stmt.where(Report.type == type)
        if status is not None:
            stmt = stmt.where(Report.status == status)
        if period_start is not None:
            stmt = stmt.where(Report.period_start >= period_start)
        if period_end is not None:
            stmt = stmt.where(Report.period_end <= period_end)

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_with_payload(self, id: UUID) -> Report | None:
        """Obtiene un reporte por ID incluyendo su payload (para GET detail)."""
        stmt = self._base_select().where(Report.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
