"""Modelo Tenant."""
import enum
from uuid import UUID

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class PlanType(str, enum.Enum):
    """Planes de suscripción."""
    FREE = "free"
    STARTER = "starter"
    GROWTH = "growth"
    ENTERPRISE = "enterprise"


class Tenant(Base, UUIDMixin, TimestampMixin):
    """Organización/Tenant."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    plan: Mapped[PlanType] = mapped_column(default=PlanType.FREE, nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name={self.name}, slug={self.slug})>"