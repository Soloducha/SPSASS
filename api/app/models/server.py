"""Modelo Server."""
import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin, TenantAwareMixin


class ServerStatus(str, enum.Enum):
    """Estado del servidor."""
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class Server(Base, UUIDMixin, TimestampMixin, TenantAwareMixin):
    """Servidor monitoreado."""

    __tablename__ = "servers"

    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv4 o IPv6
    os: Mapped[str | None] = mapped_column(String(100), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[ServerStatus] = mapped_column(default=ServerStatus.UNKNOWN, nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(nullable=True)
    alert_channels: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Relaciones
    services: Mapped[list["Service"]] = relationship(
        "Service", back_populates="server", lazy="selectin", cascade="all, delete-orphan"
    )
    processes: Mapped[list["Process"]] = relationship(
        "Process", back_populates="server", lazy="selectin", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["Job"]] = relationship(
        "Job", back_populates="server", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Server(id={self.id}, hostname={self.hostname}, status={self.status})>"