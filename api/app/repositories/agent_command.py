"""Repositorio para AgentCommand con scoping de tenant."""
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, TypedDict, Unpack
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import InstrumentedAttribute

from app.models.agent_command import AgentCommand, AgentCommandStatus
from app.repositories.base import TenantScopedRepository


class SetResultParams(TypedDict, total=False):
    """Parámetros opcionales para actualizar el resultado de un comando."""
    exit_code: int | None
    output_tail: str | None
    finished_at: datetime | None


class AgentCommandRepository(TenantScopedRepository):
    """Repositorio concreto para AgentCommand."""

    model = AgentCommand

    async def list_pending_for_server(
        self, server_id: UUID, *, limit: int = 50
    ) -> Sequence[AgentCommand]:
        """Lista comandos pendientes para un servidor, ordenados por scheduled_at."""
        stmt = (
            self._base_select()
            .where(AgentCommand.server_id == server_id)
            .where(AgentCommand.status == AgentCommandStatus.PENDING)
            .where(AgentCommand.scheduled_at <= datetime.now(UTC))
            .order_by(AgentCommand.scheduled_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def mark_running(
        self, command_ids: list[UUID], *, started_at: datetime | None = None
    ) -> int:
        """Marca comandos como RUNNING y setea started_at."""
        if not command_ids:
            return 0
        if started_at is None:
            started_at = datetime.now(UTC)
        stmt = (
            update(AgentCommand)
            .where(AgentCommand.id.in_(command_ids))
            .where(AgentCommand.tenant_id == self._tenant_id)
            .values(status=AgentCommandStatus.RUNNING, started_at=started_at, updated_at=datetime.now(UTC))
        )
        result = await self.session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined, no-any-return]

    async def set_result(
        self,
        command_id: UUID,
        tenant_id: UUID,
        *,
        status: AgentCommandStatus,
        **kwargs: Unpack[SetResultParams],
    ) -> AgentCommand | None:
        """Actualiza el resultado de un comando."""
        finished_at = kwargs.get("finished_at") or datetime.now(UTC)
        update_data: dict[str, Any] = {
            "status": status,
            "finished_at": finished_at,
            "updated_at": datetime.now(UTC),
        }
        if (exit_code := kwargs.get("exit_code")) is not None:
            update_data["exit_code"] = exit_code
        if (output_tail := kwargs.get("output_tail")) is not None:
            update_data["output_tail"] = output_tail

        stmt = (
            update(AgentCommand)
            .where(AgentCommand.id == command_id)
            .where(AgentCommand.tenant_id == tenant_id)
            .values(**update_data)
        )
        result = await self.session.execute(stmt)
        if result.rowcount == 0:  # type: ignore[attr-defined]
            return None

        # Fetch the updated command (RETURNING not reliable on SQLite)
        return await self.get(command_id)

    async def has_pending_for_entity(
        self, server_id: UUID, entity_type: str, entity_name: str
    ) -> bool:
        """Verifica si hay un comando pendiente/running para la misma entidad."""
        stmt = (
            select(func.count())
            .select_from(AgentCommand)
            .where(AgentCommand.server_id == server_id)
            .where(AgentCommand.entity_type == entity_type)
            .where(AgentCommand.entity_name == entity_name)
            .where(AgentCommand.status.in_([AgentCommandStatus.PENDING, AgentCommandStatus.RUNNING]))
            .where(AgentCommand.tenant_id == self._tenant_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def list_all(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: InstrumentedAttribute[Any] | None = None,
        **filters: object,
    ) -> Sequence[AgentCommand]:
        """Lista comandos con paginación y filtros opcionales + tenant."""
        if order_by is None:
            stmt = self._base_select().filter_by(**filters).order_by(AgentCommand.created_at.desc())
            stmt = stmt.offset(offset).limit(limit)
            result = await self.session.execute(stmt)
            return result.scalars().all()
        return await super().list_all(offset=offset, limit=limit, order_by=order_by, **filters)
