"""Modelos AlertRule, Alert, AlertDelivery."""
import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantAwareMixin, TimestampMixin, UUIDMixin


class AlertSeverity(enum.StrEnum):
    """Severidad de alerta."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(enum.StrEnum):
    """Estado de alerta."""
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertOperator(enum.StrEnum):
    """Operadores para reglas de alerta."""
    GT = "gt"      # >
    GTE = "gte"    # >=
    LT = "lt"      # <
    LTE = "lte"    # <=
    EQ = "eq"      # ==
    NEQ = "neq"    # !=


class EntityType(enum.StrEnum):
    """Tipo de entidad monitoreada."""
    SERVER = "server"
    SERVICE = "service"
    PROCESS = "process"
    JOB = "job"
    METRIC = "metric"


class AlertRule(Base, UUIDMixin, TimestampMixin, TenantAwareMixin):
    """Regla de alerta."""

    __tablename__ = "alert_rules"

    entity_type: Mapped[EntityType] = mapped_column(
        SAEnum(EntityType, name="entity_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    entity_id: Mapped[UUID | None] = mapped_column(nullable=True)  # None = aplica a todas
    metric: Mapped[str] = mapped_column(String(100), nullable=False)  # nombre de la métrica
    operator: Mapped[AlertOperator] = mapped_column(
        SAEnum(AlertOperator, name="alert_operator", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    threshold: Mapped[float] = mapped_column(nullable=False)
    duration_s: Mapped[int] = mapped_column(default=60, nullable=False)  # duración para disparar
    severity: Mapped[AlertSeverity] = mapped_column(
        SAEnum(AlertSeverity, name="alert_severity", values_callable=lambda e: [m.value for m in e]),
        default=AlertSeverity.WARNING,
        nullable=False,
    )
    channels: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # config de canales
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relaciones
    alerts: Mapped[list["Alert"]] = relationship(
        "Alert", back_populates="rule", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<AlertRule(id={self.id}, metric={self.metric}, threshold={self.threshold})>"


class Alert(Base, UUIDMixin, TimestampMixin, TenantAwareMixin):
    """Alerta disparada."""

    __tablename__ = "alerts"

    rule_id: Mapped[UUID] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    server_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("servers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        SAEnum(AlertSeverity, name="alert_severity", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    status: Mapped[AlertStatus] = mapped_column(
        SAEnum(AlertStatus, name="alert_status", values_callable=lambda e: [m.value for m in e]),
        default=AlertStatus.OPEN,
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(nullable=True)
    acknowledged_by: Mapped[UUID | None] = mapped_column(nullable=True)
    value_at_trigger: Mapped[float] = mapped_column(nullable=False)

    # Relaciones
    rule: Mapped["AlertRule"] = relationship("AlertRule", back_populates="alerts", lazy="selectin")
    deliveries: Mapped[list["AlertDelivery"]] = relationship(
        "AlertDelivery", back_populates="alert", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Alert(id={self.id}, rule_id={self.rule_id}, severity={self.severity}, status={self.status})>"


class AlertDelivery(Base, UUIDMixin, TimestampMixin, TenantAwareMixin):
    """Entrega de alerta por canal."""

    __tablename__ = "alert_deliveries"

    alert_id: Mapped[UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)  # telegram, whatsapp, email
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # pending, sent, failed
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)  # message_id, etc.
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relaciones
    alert: Mapped["Alert"] = relationship("Alert", back_populates="deliveries", lazy="selectin")

    def __repr__(self) -> str:
        return f"<AlertDelivery(id={self.id}, alert_id={self.alert_id}, channel={self.channel}, status={self.status})>"
