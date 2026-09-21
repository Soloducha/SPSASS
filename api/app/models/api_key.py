"""Modelo ApiKey para autenticación de agentes."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ApiKey(Base, UUIDMixin, TimestampMixin):
    """API Key para agentes (autenticación máquina a máquina)."""

    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_api_key_tenant_name"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # Último uso (timestamp)

    # Relaciones
    tenant: Mapped["Tenant"] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return f"<ApiKey(id={self.id}, tenant_id={self.tenant_id}, name={self.name})>"