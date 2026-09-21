"""Modelo TenantMember (para MSP - usuario en múltiples tenants)."""
import enum
from uuid import UUID

from sqlalchemy import Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class MemberRole(str, enum.Enum):
    """Roles de miembro en tenant."""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class TenantMember(Base, UUIDMixin, TimestampMixin):
    """Membresía de usuario en tenant (para MSP)."""

    __tablename__ = "tenant_members"
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_tenant_member_user_tenant"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MemberRole] = mapped_column(
        SAEnum(MemberRole, name="member_role", values_callable=lambda e: [m.value for m in e]),
        default=MemberRole.MEMBER,
        nullable=False,
    )

    # Relaciones
    user: Mapped["User"] = relationship("User", back_populates="tenant_memberships", lazy="selectin")
    tenant: Mapped["Tenant"] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return f"<TenantMember(user_id={self.user_id}, tenant_id={self.tenant_id}, role={self.role})>"