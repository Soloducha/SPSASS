"""Modelo Metric (TimescaleDB hypertable)."""
import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import Enum as SAEnum, JSON, String, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantAwareMixin


class MetricType(str, enum.Enum):
    """Tipos de métricas soportados."""
    CPU_USAGE = "cpu_usage"
    MEM_USAGE = "mem_usage"
    DISK_USAGE = "disk_usage"
    LOAD_AVG_1 = "load_avg1"
    LOAD_AVG_5 = "load_avg5"
    LOAD_AVG_15 = "load_avg15"


class Metric(Base, TenantAwareMixin):
    """Métrica de serie temporal (TimescaleDB hypertable)."""

    __tablename__ = "metrics"
    __table_args__ = (
        Index("ix_metrics_server_id_ts", "server_id", "ts"),
        Index("ix_metrics_tenant_id_ts", "tenant_id", "ts"),
        Index("ix_metrics_type_ts", "type", "ts"),
        # Nota: TimescaleDB hypertable se crea via migración SQL raw
    )

    # PK compuesta para hypertable: (ts, server_id) - TimescaleDB requiere timestamp en PK
    ts: Mapped[datetime] = mapped_column(nullable=False, primary_key=True)
    server_id: Mapped[UUID] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    type: Mapped[MetricType] = mapped_column(
        SAEnum(MetricType, name="metric_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    value: Mapped[float] = mapped_column(nullable=False)
    tags: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Relación
    server: Mapped["Server"] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return f"<Metric(ts={self.ts}, server_id={self.server_id}, type={self.type}, value={self.value})>"