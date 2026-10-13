"""Servicio para gestión de Beta Cerrada (T5 - Mes 6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import SessionDep
from app.core.beta.models import (
    PilotFeedback,
    PilotMetricsSnapshot,
    PilotStatus,
    PilotTenant,
)
from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)
settings = get_settings()


class BetaService:
    """Servicio para gestión de pilotos en beta cerrada."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ──────────────────────────────────────────────
    # Pilot Tenant Management
    # ──────────────────────────────────────────────

    async def add_pilot(
        self,
        tenant_id: UUID,
        invited_by_id: UUID | None = None,
        notes: str | None = None,
    ) -> PilotTenant:
        """
        Agrega un tenant como piloto de la beta.
        
        Args:
            tenant_id: ID del tenant a agregar
            invited_by_id: ID del usuario que invita (admin)
            notes: Notas internas
            
        Returns:
            PilotTenant creado
        """
        # Verificar si ya es piloto
        existing = await self.session.execute(
            select(PilotTenant).where(PilotTenant.tenant_id == tenant_id)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Tenant {tenant_id} ya es piloto")

        pilot = PilotTenant(
            tenant_id=tenant_id,
            status=PilotStatus.PENDING,
            invited_by_id=invited_by_id,
            notes=notes,
        )
        self.session.add(pilot)
        await self.session.flush()

        logger.info("pilot_added", tenant_id=str(tenant_id), invited_by=str(invited_by_id) if invited_by_id else None)
        return pilot

    async def remove_pilot(self, tenant_id: UUID) -> bool:
        """Remueve un tenant de la beta."""
        result = await self.session.execute(
            select(PilotTenant).where(PilotTenant.tenant_id == tenant_id)
        )
        pilot = result.scalar_one_or_none()
        if not pilot:
            return False

        pilot.status = PilotStatus.REMOVED
        await self.session.flush()
        return True

    async def get_pilot(self, tenant_id: UUID) -> PilotTenant | None:
        """Obtiene info de piloto por tenant_id."""
        result = await self.session.execute(
            select(PilotTenant).where(PilotTenant.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def list_pilots(
        self,
        status: PilotStatus | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[PilotTenant]:
        """Lista pilotos con filtros opcionales."""
        stmt = select(PilotTenant).order_by(PilotTenant.created_at.desc())
        if status:
            stmt = stmt.where(PilotTenant.status == status)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_pilots(self, status: PilotStatus | None = None) -> int:
        """Cuenta pilotos."""
        stmt = select(func.count(PilotTenant.id))
        if status:
            stmt = stmt.where(PilotTenant.status == status)
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    async def onboard_pilot(self, tenant_id: UUID) -> PilotTenant | None:
        """Marca piloto como onboarded (completó onboarding)."""
        result = await self.session.execute(
            select(PilotTenant).where(PilotTenant.tenant_id == tenant_id)
        )
        pilot = result.scalar_one_or_none()
        if not pilot:
            return None

        pilot.status = PilotStatus.ACTIVE
        pilot.onboarded_at = datetime.now(UTC)
        await self.session.flush()

        logger.info("pilot_onboarded", tenant_id=str(tenant_id))
        return pilot

    async def complete_pilot(self, tenant_id: UUID) -> PilotTenant | None:
        """Marca piloto como completado (dio feedback final)."""
        result = await self.session.execute(
            select(PilotTenant).where(PilotTenant.tenant_id == tenant_id)
        )
        pilot = result.scalar_one_or_none()
        if not pilot:
            return None

        pilot.status = PilotStatus.COMPLETED
        pilot.completed_at = datetime.now(UTC)
        await self.session.flush()
        return pilot

    # ──────────────────────────────────────────────
    # Feedback
    # ──────────────────────────────────────────────

    async def submit_feedback(
        self,
        pilot_id: UUID,
        category: str,
        title: str,
        description: str,
        user_id: UUID | None = None,
        user_email: str | None = None,
        rating: int | None = None,
        page_url: str | None = None,
        user_agent: str | None = None,
        screen_resolution: str | None = None,
    ) -> PilotFeedback:
        """Registra feedback de un piloto."""
        feedback = PilotFeedback(
            pilot_id=pilot_id,
            user_id=user_id,
            user_email=user_email,
            category=category,
            title=title,
            description=description,
            rating=rating,
            page_url=page_url,
            user_agent=user_agent,
            screen_resolution=screen_resolution,
        )
        self.session.add(feedback)
        await self.session.flush()

        logger.info("pilot_feedback_submitted", pilot_id=str(pilot_id), category=category, rating=rating)
        return feedback

    async def list_feedback(
        self,
        pilot_id: UUID | None = None,
        status: str | None = None,
        category: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[PilotFeedback]:
        """Lista feedback con filtros."""
        stmt = select(PilotFeedback).order_by(PilotFeedback.created_at.desc())
        if pilot_id:
            stmt = stmt.where(PilotFeedback.pilot_id == pilot_id)
        if status:
            stmt = stmt.where(PilotFeedback.status == status)
        if category:
            stmt = stmt.where(PilotFeedback.category == category)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ──────────────────────────────────────────────
    # Metrics Snapshots
    # ──────────────────────────────────────────────

    async def record_daily_metrics(
        self,
        pilot_id: UUID,
        date: datetime | None = None,
        **metrics,
    ) -> PilotMetricsSnapshot:
        """
        Registra snapshot diario de métricas.
        Upsert: si ya existe para ese pilot+date, actualiza.
        """
        if date is None:
            date = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        # Buscar existente
        result = await self.session.execute(
            select(PilotMetricsSnapshot).where(
                and_(
                    PilotMetricsSnapshot.pilot_id == pilot_id,
                    PilotMetricsSnapshot.date == date,
                )
            )
        )
        snapshot = result.scalar_one_or_none()

        if snapshot:
            # Actualizar
            for key, value in metrics.items():
                if hasattr(snapshot, key):
                    setattr(snapshot, key, value)
        else:
            # Crear nuevo
            snapshot = PilotMetricsSnapshot(
                pilot_id=pilot_id,
                date=date,
                **metrics,
            )
            self.session.add(snapshot)

        await self.session.flush()
        return snapshot

    async def get_metrics_range(
        self,
        pilot_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> list[PilotMetricsSnapshot]:
        """Obtiene métricas en rango de fechas."""
        result = await self.session.execute(
            select(PilotMetricsSnapshot).where(
                and_(
                    PilotMetricsSnapshot.pilot_id == pilot_id,
                    PilotMetricsSnapshot.date >= start_date,
                    PilotMetricsSnapshot.date <= end_date,
                )
            ).order_by(PilotMetricsSnapshot.date)
        )
        return list(result.scalars().all())

    async def get_aggregated_metrics(
        self,
        pilot_id: UUID | None = None,
        days: int = 30,
    ) -> dict:
        """
        Obtiene métricas agregadas (últimos N días).
        Si pilot_id es None, agrega todos los pilotos activos.
        """
        end_date = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = end_date - timedelta(days=days)

        stmt = select(
            func.sum(PilotMetricsSnapshot.dau).label("total_dau"),
            func.sum(PilotMetricsSnapshot.servers_count).label("total_servers"),
            func.sum(PilotMetricsSnapshot.api_keys_count).label("total_api_keys"),
            func.sum(PilotMetricsSnapshot.alerts_triggered).label("total_alerts_triggered"),
            func.sum(PilotMetricsSnapshot.alerts_resolved).label("total_alerts_resolved"),
            func.sum(PilotMetricsSnapshot.reports_generated).label("total_reports"),
            func.sum(PilotMetricsSnapshot.invitations_sent).label("total_invitations_sent"),
            func.sum(PilotMetricsSnapshot.invitations_accepted).label("total_invitations_accepted"),
            func.sum(PilotMetricsSnapshot.members_count).label("total_members"),
            func.sum(PilotMetricsSnapshot.total_sessions).label("total_sessions"),
            func.avg(PilotMetricsSnapshot.avg_session_duration_seconds).label("avg_session_duration"),
        ).where(
            and_(
                PilotMetricsSnapshot.date >= start_date,
                PilotMetricsSnapshot.date <= end_date,
            )
        )

        if pilot_id:
            stmt = stmt.where(PilotMetricsSnapshot.pilot_id == pilot_id)
        else:
            # Solo pilotos activos
            stmt = stmt.join(PilotTenant).where(PilotTenant.status == PilotStatus.ACTIVE)

        result = await self.session.execute(stmt)
        row = result.one()

        return {
            "period_days": days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_dau": row.total_dau or 0,
            "total_servers": row.total_servers or 0,
            "total_api_keys": row.total_api_keys or 0,
            "total_alerts_triggered": row.total_alerts_triggered or 0,
            "total_alerts_resolved": row.total_alerts_resolved or 0,
            "total_reports": row.total_reports or 0,
            "total_invitations_sent": row.total_invitations_sent or 0,
            "total_invitations_accepted": row.total_invitations_accepted or 0,
            "total_members": row.total_members or 0,
            "total_sessions": row.total_sessions or 0,
            "avg_session_duration_seconds": row.avg_session_duration or 0.0,
        }

    # ──────────────────────────────────────────────
    # Feature Flag Checks
    # ──────────────────────────────────────────────

    @staticmethod
    def is_beta_enabled() -> bool:
        """Verifica si la beta está habilitada globalmente."""
        return settings.BETA_ENABLED

    @staticmethod
    def is_feedback_enabled() -> bool:
        """Verifica si el feedback widget está habilitado."""
        return settings.BETA_ENABLED and settings.BETA_FEEDBACK_ENABLED

    @staticmethod
    def is_metrics_enabled() -> bool:
        """Verifica si la recolección de métricas está habilitada."""
        return settings.BETA_ENABLED and settings.BETA_METRICS_ENABLED

    async def is_tenant_pilot(self, tenant_id: UUID) -> bool:
        """Verifica si un tenant es piloto activo."""
        if not self.is_beta_enabled():
            return False

        result = await self.session.execute(
            select(PilotTenant.id).where(
                and_(
                    PilotTenant.tenant_id == tenant_id,
                    PilotTenant.status.in_([PilotStatus.ACTIVE, PilotStatus.PENDING]),
                )
            )
        )
        return result.scalar_one_or_none() is not None


# ──────────────────────────────────────────────
# Dependency para FastAPI
# ──────────────────────────────────────────────

async def get_beta_service(session: SessionDep) -> BetaService:
    """Dependency para inyectar BetaService."""
    return BetaService(session)
