"""Modelos para Beta Cerrada (T5 - Mes 6)."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    pass


class PilotStatus(enum.StrEnum):
    """Estado del piloto en la beta."""
    PENDING = "pending"       # Invitado, pendiente de onboarding
    ACTIVE = "active"         # Onboarded, usando el producto
    INACTIVE = "inactive"     # No usa el producto (churn risk)
    COMPLETED = "completed"   # Beta completada, feedback dado
    REMOVED = "removed"       # Removido de la beta


class PilotTenant(Base, UUIDMixin, TimestampMixin):
    """Tenant participante en la beta cerrada."""

    __tablename__ = "pilot_tenants"

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True
    )
    status: Mapped[PilotStatus] = mapped_column(
        SAEnum(PilotStatus, name="pilot_status", values_callable=lambda e: [m.value for m in e]),
        default=PilotStatus.PENDING,
        nullable=False,
        index=True,
    )
    invited_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Relaciones
    feedback_entries: Mapped[list[PilotFeedback]] = relationship(
        "PilotFeedback", back_populates="pilot", lazy="selectin", cascade="all, delete-orphan"
    )
    metrics_snapshots: Mapped[list[PilotMetricsSnapshot]] = relationship(
        "PilotMetricsSnapshot", back_populates="pilot", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PilotTenant(tenant_id={self.tenant_id}, status={self.status.value})>"


class PilotFeedback(Base, UUIDMixin, TimestampMixin):
    """Feedback de pilotos (widget in-app)."""

    __tablename__ = "pilot_feedback"

    pilot_id: Mapped[UUID] = mapped_column(
        ForeignKey("pilot_tenants.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True
    )
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Tipo de feedback
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # bug, feature, ux, performance, other
    rating: Mapped[int | None] = mapped_column(nullable=True)  # 1-5 (NPS style)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Contexto técnico
    page_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    screen_resolution: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Estado
    status: Mapped[str] = mapped_column(String(50), default="new", nullable=False, index=True)  # new, triaged, in_progress, done, wont_fix
    assigned_to: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relaciones
    pilot: Mapped[PilotTenant] = relationship("PilotTenant", back_populates="feedback_entries", lazy="selectin")

    def __repr__(self) -> str:
        return f"<PilotFeedback(pilot_id={self.pilot_id}, category={self.category}, rating={self.rating})>"


class PilotMetricsSnapshot(Base, UUIDMixin, TimestampMixin):
    """Snapshot diario de métricas de adopción por piloto."""

    __tablename__ = "pilot_metrics_snapshots"

    pilot_id: Mapped[UUID] = mapped_column(
        ForeignKey("pilot_tenants.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)  # Fecha del snapshot (UTC midnight)

    # Métricas de adopción
    dau: Mapped[int] = mapped_column(default=0, nullable=False)  # Daily Active Users
    servers_count: Mapped[int] = mapped_column(default=0, nullable=False)
    api_keys_count: Mapped[int] = mapped_column(default=0, nullable=False)
    alerts_triggered: Mapped[int] = mapped_column(default=0, nullable=False)
    alerts_resolved: Mapped[int] = mapped_column(default=0, nullable=False)
    reports_generated: Mapped[int] = mapped_column(default=0, nullable=False)
    invitations_sent: Mapped[int] = mapped_column(default=0, nullable=False)
    invitations_accepted: Mapped[int] = mapped_column(default=0, nullable=False)
    members_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # Sesiones
    total_sessions: Mapped[int] = mapped_column(default=0, nullable=False)
    avg_session_duration_seconds: Mapped[float] = mapped_column(default=0.0, nullable=False)

    # Features usadas (JSON para flexibilidad)
    features_used: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Relaciones
    pilot: Mapped[PilotTenant] = relationship("PilotTenant", back_populates="metrics_snapshots", lazy="selectin")

    def __repr__(self) -> str:
        return f"<PilotMetricsSnapshot(pilot_id={self.pilot_id}, date={self.date.date()}, dau={self.dau})>"
