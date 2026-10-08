"""Modelo TenantInvitation: invitacion por email para unirse a un tenant."""
import enum
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.tenant_member import MemberRole

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class InvitationStatus(enum.StrEnum):
    """Estado derivado de una invitacion."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"


class TenantInvitation(Base, UUIDMixin, TimestampMixin):
    """Invitacion pendiente para unirse a un tenant con un rol concreto.

    El `token` es un JWT firmado con el mismo secreto que los access tokens
    (`type="invitation"`), de modo que la aceptacion es stateless: el token
    viaja en el link del email y la fila en BD es la fuente de verdad sobre
    aceptacion/duplicados.
    """

    __tablename__ = "tenant_invitations"
    __table_args__ = (
        # Solo una invitacion *pendiente* por (tenant, email). Se usa indice
        # parcial en vez de UNIQUEConstraint para permitir re-invitar a alguien
        # que ya acepto (accepted_at pasa a NOT NULL y libera la fila).
        Index(
            "uq_tenant_invitation_pending",
            "tenant_id",
            "email",
            unique=True,
            sqlite_where=text("accepted_at IS NULL"),
            postgresql_where=text("accepted_at IS NULL"),
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[MemberRole] = mapped_column(
        SAEnum(MemberRole, name="member_role", values_callable=lambda e: [m.value for m in e]),
        default=MemberRole.MEMBER,
        nullable=False,
    )
    token: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invited_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relaciones
    tenant: Mapped["Tenant"] = relationship(lazy="selectin")

    @property
    def is_expired(self) -> bool:
        """True cuando la ventana de aceptacion ya paso."""
        now = datetime.now(UTC)
        expires = self.expires_at
        if expires.tzinfo is None:
            # SQLite (y algunos drivers) devuelven naive aunque la columna
            # sea timezone-aware: normalizamos para no comparar con error.
            expires = expires.replace(tzinfo=UTC)
        return now >= expires

    def __repr__(self) -> str:
        return (
            f"<TenantInvitation(id={self.id}, tenant_id={self.tenant_id}, "
            f"email={self.email}, role={self.role})>"
        )
