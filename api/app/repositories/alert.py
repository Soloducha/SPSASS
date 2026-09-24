"""Repositorios para alertas con scoping de tenant."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import desc, func, select

from app.models.alert import Alert, AlertRule, AlertSeverity, AlertStatus
from app.repositories.base import TenantScopedRepository


class AlertRuleRepository(TenantScopedRepository):
    """Repositorio concreto para AlertRule."""

    model = AlertRule


class AlertRepository(TenantScopedRepository):
    """Repositorio concreto para Alert con métodos de consulta adicionales."""

    model = Alert

    async def list_filtered(
        self,
        *,
        status: AlertStatus | None = None,
        severity: AlertSeverity | None = None,
        rule_id: UUID | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Alert]:
        """Lista alertas con filtros opcionales, ordenadas por triggered_at desc."""
        stmt = self._base_select().order_by(desc(Alert.triggered_at))  # type: ignore[attr-defined]
        if status is not None:
            stmt = stmt.where(Alert.status == status)
        if severity is not None:
            stmt = stmt.where(Alert.severity == severity)
        if rule_id is not None:
            stmt = stmt.where(Alert.rule_id == rule_id)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_filtered(
        self,
        *,
        status: AlertStatus | None = None,
        severity: AlertSeverity | None = None,
        rule_id: UUID | None = None,
    ) -> int:
        """Cuenta alertas con filtros opcionales."""
        stmt = select(func.count()).select_from(Alert).where(Alert.tenant_id == self._tenant_id)
        if status is not None:
            stmt = stmt.where(Alert.status == status)
        if severity is not None:
            stmt = stmt.where(Alert.severity == severity)
        if rule_id is not None:
            stmt = stmt.where(Alert.rule_id == rule_id)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def acknowledge(self, alert_id: UUID, acknowledged_by: UUID) -> Alert | None:
        """Marca una alerta como acknowledged."""
        alert = await self.get(alert_id)
        if not alert:
            return None
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.now(UTC)
        alert.acknowledged_by = acknowledged_by
        await self.session.flush()
        await self.session.refresh(alert)
        return alert  # type: ignore[no-any-return]

    async def resolve(self, alert_id: UUID) -> Alert | None:
        """Marca una alerta como resolved."""
        alert = await self.get(alert_id)
        if not alert:
            return None
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(alert)
        return alert  # type: ignore[no-any-return]
