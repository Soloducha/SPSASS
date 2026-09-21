"""Modelo Process."""
from uuid import UUID

from sqlalchemy import JSON, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin, TenantAwareMixin


class Process(Base, UUIDMixin, TimestampMixin, TenantAwareMixin):
    """Proceso monitoreado por patrón."""

    __tablename__ = "processes"

    server_id: Mapped[UUID] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    pattern: Mapped[str] = mapped_column(String(500), nullable=False)  # regex pattern
    expected_count: Mapped[int] = mapped_column(default=1, nullable=False)
    auto_restart: Mapped[bool] = mapped_column(default=False, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Relaciones
    server: Mapped["Server"] = relationship("Server", back_populates="processes", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Process(id={self.id}, name={self.name}, pattern={self.pattern})>"