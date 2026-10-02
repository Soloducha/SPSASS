"""Modelo AgentCommand para auto-restart."""
import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantAwareMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.server import Server


class AgentCommandEntityType(enum.StrEnum):
    """Tipo de entidad a reiniciar."""
    SERVICE = "service"
    PROCESS = "process"


class AgentCommandStatus(enum.StrEnum):
    """Estado del comando."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class AgentCommand(Base, UUIDMixin, TimestampMixin, TenantAwareMixin):
    """Comando pendiente para el agente (auto-restart)."""

    __tablename__ = "agent_commands"

    server_id: Mapped[UUID] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[AgentCommandEntityType] = mapped_column(
        SAEnum(AgentCommandEntityType, name="agent_command_entity_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    command: Mapped[str | None] = mapped_column(String(500), nullable=True)  # override opcional
    status: Mapped[AgentCommandStatus] = mapped_column(
        SAEnum(AgentCommandStatus, name="agent_command_status", values_callable=lambda e: [m.value for m in e]),
        default=AgentCommandStatus.PENDING,
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=3, nullable=False)
    backoff_s: Mapped[int] = mapped_column(default=60, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(nullable=True)
    output_tail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relaciones
    server: Mapped["Server"] = relationship("Server", back_populates="agent_commands", lazy="selectin")

    def __repr__(self) -> str:
        return f"<AgentCommand(id={self.id}, server_id={self.server_id}, entity={self.entity_type.value}:{self.entity_name}, status={self.status.value})>"
