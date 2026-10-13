#!/usr/bin/env python
"""Script de agregación diaria de métricas de adopción para pilotos beta.

Uso:
    python scripts/daily_metrics_snapshot.py              # Para ayer (default)
    python scripts/daily_metrics_snapshot.py --date 2026-10-12
    python scripts/daily_metrics_snapshot.py --all-pilots --date 2026-10-12
    python scripts/daily_metrics_snapshot.py --backfill 7 # Últimos 7 días

Opciones:
    --sqlite    Usar SQLite en memoria (para desarrollo local sin PostgreSQL)

Ejecutar via cron/k8s cronjob diario a las 00:30 UTC.
"""

import argparse
import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.session import get_db_session, init_db, Base
from app.models.alert import Alert, AlertStatus
from app.models.api_key import ApiKey
from app.models.metric import MetricType
from app.core.beta.models import PilotMetricsSnapshot, PilotStatus, PilotTenant
from app.models.report import Report, ReportStatus
from app.models.server import Server
from app.models.tenant_invitation import TenantInvitation
from app.models.tenant_member import TenantMember
from app.models.user import User

# Global session factory
_async_session_factory = None


async def init_db_with_mode(use_sqlite: bool = False):
    """Inicializa DB con SQLite en memoria o PostgreSQL según flag."""
    global _async_session_factory
    
    if use_sqlite:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    else:
        await init_db()
        _async_session_factory = get_db_session


def get_session() -> AsyncSession:
    if _async_session_factory is None:
        raise RuntimeError("DB no inicializada. Llamar init_db_with_mode() primero.")
    return _async_session_factory()


async def compute_metrics_for_pilot(
    session: AsyncSession,
    pilot: PilotTenant,
    target_date: date,
) -> dict:
    """Calcula todas las métricas para un piloto en una fecha dada."""
    tenant_id = pilot.tenant_id
    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=UTC)
    day_end = day_start + timedelta(days=1)

    # ──────────────────────────────────────────────
    # DAU: usuarios únicos con actividad (métricas, alerts, logins)
    # ──────────────────────────────────────────────
    # Usamos metric_rollups como proxy de actividad del servidor
    # y users.last_login_at para actividad humana
    dau_result = await session.execute(
        text("""
            SELECT COUNT(DISTINCT u.id)
            FROM users u
            JOIN tenant_members tm ON u.id = tm.user_id
            WHERE tm.tenant_id = :tenant_id
              AND u.last_login_at >= :day_start
              AND u.last_login_at < :day_end
        """),
        {"tenant_id": tenant_id, "day_start": day_start, "day_end": day_end},
    )
    dau = dau_result.scalar() or 0

    # ──────────────────────────────────────────────
    # Servers count
    # ──────────────────────────────────────────────
    servers_result = await session.execute(
        select(func.count(Server.id)).where(Server.tenant_id == tenant_id)
    )
    servers_count = servers_result.scalar() or 0

    # ──────────────────────────────────────────────
    # API keys count
    # ──────────────────────────────────────────────
    api_keys_result = await session.execute(
        select(func.count(ApiKey.id)).where(ApiKey.tenant_id == tenant_id)
    )
    api_keys_count = api_keys_result.scalar() or 0

    # ──────────────────────────────────────────────
    # Alerts triggered/resolved this day
    # ──────────────────────────────────────────────
    alerts_triggered_result = await session.execute(
        select(func.count(Alert.id)).where(
            Alert.tenant_id == tenant_id,
            Alert.triggered_at >= day_start,
            Alert.triggered_at < day_end,
        )
    )
    alerts_triggered = alerts_triggered_result.scalar() or 0

    alerts_resolved_result = await session.execute(
        select(func.count(Alert.id)).where(
            Alert.tenant_id == tenant_id,
            Alert.resolved_at >= day_start,
            Alert.resolved_at < day_end,
            Alert.status == AlertStatus.RESOLVED,
        )
    )
    alerts_resolved = alerts_resolved_result.scalar() or 0

    # ──────────────────────────────────────────────
    # Reports generated this day
    # ──────────────────────────────────────────────
    reports_result = await session.execute(
        select(func.count(Report.id)).where(
            Report.tenant_id == tenant_id,
            Report.generated_at >= day_start,
            Report.generated_at < day_end,
            Report.status == ReportStatus.COMPLETED,
        )
    )
    reports_generated = reports_result.scalar() or 0

    # ──────────────────────────────────────────────
    # Invitations sent/accepted this day
    # ──────────────────────────────────────────────
    invitations_sent_result = await session.execute(
        select(func.count()).select_from(
            select(TenantInvitation.id).where(
                TenantInvitation.tenant_id == tenant_id,
                TenantInvitation.created_at >= day_start,
                TenantInvitation.created_at < day_end,
            ).subquery()
        )
    )
    invitations_sent = invitations_sent_result.scalar() or 0

    invitations_accepted_result = await session.execute(
        select(func.count()).select_from(
            select(TenantInvitation.id).where(
                TenantInvitation.tenant_id == tenant_id,
                TenantInvitation.accepted_at >= day_start,
                TenantInvitation.accepted_at < day_end,
            ).subquery()
        )
    )
    invitations_accepted = invitations_accepted_result.scalar() or 0

    # ──────────────────────────────────────────────
    # Members count
    # ──────────────────────────────────────────────
    members_result = await session.execute(
        select(func.count(TenantMember.id)).where(TenantMember.tenant_id == tenant_id)
    )
    members_count = members_result.scalar() or 0

    # ──────────────────────────────────────────────
    # Sessions & avg duration (placeholder - requires session tracking)
    # ──────────────────────────────────────────────
    total_sessions = 0
    avg_session_duration = 0.0

    # ──────────────────────────────────────────────
    # Features used (what parts of the product they touched)
    # ──────────────────────────────────────────────
    features_used = {
        "servers": servers_count > 0,
        "alerts": alerts_triggered > 0,
        "reports": reports_generated > 0,
        "invitations": invitations_sent > 0,
        "api_keys": api_keys_count > 0,
    }

    return {
        "dau": dau,
        "servers_count": servers_count,
        "api_keys_count": api_keys_count,
        "alerts_triggered": alerts_triggered,
        "alerts_resolved": alerts_resolved,
        "reports_generated": reports_generated,
        "invitations_sent": invitations_sent,
        "invitations_accepted": invitations_accepted,
        "members_count": members_count,
        "total_sessions": total_sessions,
        "avg_session_duration_seconds": avg_session_duration,
        "features_used": features_used,
    }


async def upsert_snapshot(
    session: AsyncSession,
    pilot: PilotTenant,
    target_date: date,
    metrics: dict,
) -> PilotMetricsSnapshot:
    """Inserta o actualiza el snapshot diario."""
    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=UTC)

    # Check existing
    result = await session.execute(
        select(PilotMetricsSnapshot).where(
            PilotMetricsSnapshot.pilot_id == pilot.id,
            PilotMetricsSnapshot.date == day_start,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Update
        for key, value in metrics.items():
            setattr(existing, key, value)
        existing.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(existing)
        return existing
    else:
        # Create
        snapshot = PilotMetricsSnapshot(
            pilot_id=pilot.id,
            date=day_start,
            **metrics,
        )
        session.add(snapshot)
        await session.commit()
        await session.refresh(snapshot)
        return snapshot


async def run_snapshot(target_date: date, pilot_ids: list[UUID] | None = None) -> None:
    """Ejecuta snapshot para una fecha y lista de pilotos (o todos activos)."""
    async with get_session() as session:
        # Get pilots
        if pilot_ids:
            result = await session.execute(
                select(PilotTenant).where(PilotTenant.id.in_(pilot_ids))
            )
        else:
            # Solo pilotos activos
            result = await session.execute(
                select(PilotTenant).where(PilotTenant.status == PilotStatus.ACTIVE)
            )
        pilots = result.scalars().all()

        if not pilots:
            print(f"[WARN] No hay pilotos activos para {target_date}")
            return

        print(f"[INFO] Generando snapshots para {target_date} ({len(pilots)} pilotos)...")

        for pilot in pilots:
            metrics = await compute_metrics_for_pilot(session, pilot, target_date)
            snapshot = await upsert_snapshot(session, pilot, target_date, metrics)
            print(f"   [OK] {pilot.tenant_id} (pilot: {pilot.id[:8]}...) -- DAU: {metrics['dau']}, "
                  f"Servers: {metrics['servers_count']}, Alerts: {metrics['alerts_triggered']}, "
                  f"Reports: {metrics['reports_generated']}")

        print(f"[OK] Completado: {len(pilots)} snapshots para {target_date}")


async def backfill(days: int) -> None:
    """Backfill para los últimos N días."""
    today = datetime.now(UTC).date()
    for i in range(1, days + 1):
        target = today - timedelta(days=i)
        await run_snapshot(target)
        print()


async def main():
    parser = argparse.ArgumentParser(description="Daily pilot metrics snapshot")
    parser.add_argument("--sqlite", action="store_true", help="Usar SQLite en memoria (dev)")
    parser.add_argument("--date", help="Fecha objetivo (YYYY-MM-DD), default: ayer")
    parser.add_argument("--pilot-id", action="append", help="UUID de piloto específico (repeatable)")
    parser.add_argument("--all-pilots", action="store_true", help="Incluir pilotos no activos")
    parser.add_argument("--backfill", type=int, help="Backfill últimos N días")

    args = parser.parse_args()

    await init_db_with_mode(use_sqlite=args.sqlite)

    if args.backfill:
        await backfill(args.backfill)
        return

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        # Default: ayer
        target_date = (datetime.now(UTC) - timedelta(days=1)).date()

    pilot_ids = [UUID(pid) for pid in args.pilot_id] if args.pilot_id else None

    await run_snapshot(target_date, pilot_ids)


if __name__ == "__main__":
    asyncio.run(main())