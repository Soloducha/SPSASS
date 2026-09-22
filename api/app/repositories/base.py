"""Repositorio base con scoping de tenant automático (defensa en profundidad + RLS).

Este repositorio fuerza filtro por tenant_id en TODAS las queries.
La RLS en PostgreSQL es la red de seguridad; esto es la primera línea.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeVar, cast
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.tenant.context import require_tenant_context
from app.models.base import TenantAwareMixin

_ModelT = TypeVar("_ModelT", bound=TenantAwareMixin)


class TenantScopedRepository[ModelT]:
    """
    Repositorio base que aplica filtro de tenant automáticamente.

    Uso:
        class ServerRepository(TenantScopedRepository[Server]):
            model = Server

        repo = ServerRepository(session)
        servers = await repo.list_all()  # Solo servers del tenant actual
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._tenant_id = require_tenant_context()

    # ──────────────────────────────────────────────
    # Query building con tenant scoping automático
    # ──────────────────────────────────────────────

    def _base_select(self) -> Select:
        """Select base con filtro tenant_id = contexto actual."""
        return select(self.model).where(cast(Any, self.model).tenant_id == self._tenant_id)

    def _apply_tenant_filter(self, stmt: Select) -> Select:
        """Aplica filtro de tenant a un statement existente."""
        return stmt.where(cast(Any, self.model).tenant_id == self._tenant_id)

    # ──────────────────────────────────────────────
    # CRUD básico con tenant scoping
    # ──────────────────────────────────────────────

    async def get(self, id: UUID) -> ModelT | None:
        """Obtiene una entidad por ID (solo si pertenece al tenant actual)."""
        stmt = self._base_select().where(cast(Any, self.model).id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by(self, **filters: Any) -> ModelT | None:  # type: ignore[explicit-any]
        """Obtiene una entidad por filtros arbitrarios + tenant."""
        stmt = self._base_select().filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: InstrumentedAttribute | None = None,
        **filters: Any,  # type: ignore[explicit-any]
    ) -> Sequence[ModelT]:
        """Lista entidades con paginación y filtros opcionales + tenant."""
        stmt = self._base_select().filter_by(**filters)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self, **filters: Any) -> int:  # type: ignore[explicit-any]
        """Cuenta entidades con filtros opcionales + tenant."""
        stmt = select(func.count()).select_from(self.model).where(cast(Any, self.model).tenant_id == self._tenant_id)
        if filters:
            stmt = stmt.filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def exists(self, id: UUID) -> bool:
        """Verifica si existe una entidad (solo en tenant actual)."""
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(cast(Any, self.model).id == id, cast(Any, self.model).tenant_id == self._tenant_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def create(self, **data: Any) -> ModelT:  # type: ignore[explicit-any]
        """
        Crea una entidad forzando tenant_id del contexto actual.
        Ignora cualquier tenant_id pasado en data (seguridad).
        """
        data["tenant_id"] = self._tenant_id
        obj = self.model(**data)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, id: UUID, **data: Any) -> ModelT | None:  # type: ignore[explicit-any]
        """Actualiza una entidad (solo si pertenece al tenant actual)."""
        obj = await self.get(id)
        if not obj:
            return None

        # Nunca permitir cambiar tenant_id
        data.pop("tenant_id", None)

        for key, value in data.items():
            setattr(obj, key, value)

        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, id: UUID) -> bool:
        """Elimina una entidad (solo si pertenece al tenant actual)."""
        obj = await self.get(id)
        if not obj:
            return False

        await self.session.delete(obj)
        await self.session.flush()
        return True

    # ──────────────────────────────────────────────
    # Bulk operations con tenant scoping
    # ──────────────────────────────────────────────

    async def bulk_create(self, items: list[dict]) -> list[ModelT]:
        """Crea múltiples entidades forzando tenant_id."""
        for item in items:
            item["tenant_id"] = self._tenant_id
        objs = [self.model(**item) for item in items]
        self.session.add_all(objs)
        await self.session.flush()
        for obj in objs:
            await self.session.refresh(obj)
        return objs

    async def bulk_delete(self, ids: list[UUID]) -> int:
        """Elimina múltiples entidades (solo del tenant actual)."""
        stmt = delete(self.model).where(
            cast(Any, self.model).id.in_(ids), cast(Any, self.model).tenant_id == self._tenant_id
        )
        result = await self.session.execute(stmt)
        return cast(CursorResult, result).rowcount

    # ──────────────────────────────────────────────
    # Raw query helper (para queries complejas)
    # ──────────────────────────────────────────────

    def select(self) -> Select:
        """Retorna un SELECT base con tenant scoping para queries personalizadas."""
        return self._base_select()
