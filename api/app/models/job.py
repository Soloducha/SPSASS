"""Modelos Job y JobRun."""
import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, String, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin, TenantAwareMixin


class JobKind(str, enum.Enum):
    """Tipos de job."""
    CRON = "cron"
    BATCH = "batch"
    SCHEDULED = "scheduled"


class JobStatus(str, enum.Enum):
    """Estado del job."""
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class Job(Base, UUIDMixin, TimestampMixin, TenantAwareMixin):
    """Job programado (cron, batch, scheduled)."""

    __tablename__ = "jobs"

    server_id: Mapped[UUID] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[JobKind] = mapped_column(nullable=False)
    schedule_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)  # solo para cron
    command: Mapped[str] = mapped_column(Text, nullable=False)
    timeout_s: Mapped[int] = mapped_column(default=3600, nullable=False)  # 1 hora default
    alert_on_fail: Mapped[bool] = mapped_column(default=True, nullable=False)
    auto_restart: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[JobStatus] = mapped_column(default=JobStatus.ACTIVE, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Relaciones
    server: Mapped["Server"] = relationship("Server", back_populates="jobs", lazy="selectin")
    runs: Mapped[list["JobRun"]] = relationship(
        "JobRun", back_populates="job", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, name={self.name}, kind={self.kind}, status={self.status})>"


class JobRun(Base, UUIDMixin, TenantAwareMixin):
    """Ejecución de un job."""

    __tablename__ = "job_runs"

    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    exit_code: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # running, success, failed, timeout
    output_tail: Mapped[str | None] = mapped_column(Text, nullable=True)  # últimas líneas de output
    run_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Relaciones
    job: Mapped["Job"] = relationship("Job", back_populates="runs", lazy="selectin")

    def __repr__(self) -> str:
        return f"<JobRun(id={self.id}, job_id={self.job_id}, status={self.status})>"