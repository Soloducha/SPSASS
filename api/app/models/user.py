"""Modelo User."""
import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin, TenantAwareMixin


class UserRole(str, enum.Enum):
    """Roles de usuario dentro de un tenant."""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class User(Base, UUIDMixin, TimestampMixin, TenantAwareMixin):
    """Usuario del sistema."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(default=UserRole.MEMBER, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Relaciones
    tenant_memberships: Mapped[list["TenantMember"]] = relationship(
        "TenantMember", back_populates="user", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, tenant_id={self.tenant_id})>"