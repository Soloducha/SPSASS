"""Modelo Service."""
import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin, TenantAwareMixin


class ServiceState(str, enum.Enum):
    """Estado del servicio."""
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    UNKNOWN = "unknown"


class Service(Base, UUIDMixin, TimestampMixin, TenantAwareMixin):
    """Servicio systemd monitoreado."""

    __tablename__ = "services"

    server_id: Mapped[UUID] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    desired_state: Mapped[ServiceState] = mapped_column(default=ServiceState.RUNNING, nullable=False)
    auto_restart: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_status: Mapped[ServiceState] = mapped_column(default=ServiceState.UNKNOWN, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Relaciones
    server: Mapped["Server"] = relationship("Server", back_populates="services", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Service(id={self.id}, name={self.name}, server_id={self.server_id})>"