"""Modelo Report."""
import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin, TenantAwareMixin


class ReportType(str, enum.Enum):
    """Tipos de reporte."""
    AVAILABILITY = "availability"
    INCIDENTS = "incidents"
    ALERTS = "alerts"
    SLA = "sla"
    METRICS = "metrics"


class ReportStatus(str, enum.Enum):
    """Estado del reporte."""
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class Report(Base, UUIDMixin, TimestampMixin, TenantAwareMixin):
    """Reporte generado."""

    __tablename__ = "reports"

    period_start: Mapped[datetime] = mapped_column(nullable=False)
    period_end: Mapped[datetime] = mapped_column(nullable=False)
    type: Mapped[ReportType] = mapped_column(nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[ReportStatus] = mapped_column(default=ReportStatus.PENDING, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # path al archivo generado
    error: Mapped[str | None] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return f"<Report(id={self.id}, type={self.type}, period={self.period_start} - {self.period_end})>"