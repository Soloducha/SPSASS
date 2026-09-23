"""Modelo MetricRollup (agregaciones por período)."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantAwareMixin
from app.models.metric import MetricType

if TYPE_CHECKING:
    from app.models.server import Server


class RollupPeriod(enum.StrEnum):
    """Períodos de agregación de métricas."""

    MIN_1 = "1m"
    MIN_5 = "5m"
    HOUR_1 = "1h"
    DAY_1 = "1d"


class MetricRollup(Base, TenantAwareMixin):
    """Agregación de métricas crudas por período (buckets idempotentes).

    NO tiene RLS (igual que ``metrics``): el worker de rollups agrega
    multi-tenant y las políticas FORCE TO app_user lo romperían sin
    contexto de tenant. El aislamiento de lectura se garantiza en la capa
    de aplicación (queries con tenant_id forzado).
    """

    __tablename__ = "metric_rollups"
    __table_args__ = (
        Index("ix_metric_rollups_tenant_period_ts", "tenant_id", "period", "bucket_start"),
        Index("ix_metric_rollups_server_ts", "server_id", "bucket_start"),
    )

    # PK compuesta → upsert idempotente (un bucket por período/servidor/tipo)
    period: Mapped[RollupPeriod] = mapped_column(
        SAEnum(RollupPeriod, name="rollup_period", values_callable=lambda e: [m.value for m in e]),
        primary_key=True,
    )
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    server_id: Mapped[UUID] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True
    )
    type: Mapped[MetricType] = mapped_column(
        SAEnum(MetricType, name="metric_type", values_callable=lambda e: [m.value for m in e]),
        primary_key=True,
    )

    # Agregados
    count: Mapped[int] = mapped_column(nullable=False)
    avg: Mapped[float] = mapped_column(nullable=False)
    min: Mapped[float] = mapped_column(nullable=False)
    max: Mapped[float] = mapped_column(nullable=False)
    last: Mapped[float] = mapped_column(nullable=False)

    # Relación
    server: Mapped["Server"] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<MetricRollup(period={self.period.value}, bucket_start={self.bucket_start}, "
            f"server_id={self.server_id}, type={self.type.value}, count={self.count})>"
        )
