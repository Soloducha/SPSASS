#!/usr/bin/env python
"""Script para crear pilotos de beta cerrada.

Uso:
    python scripts/create_pilot.py <tenant_id> [--email <admin_email>] [--notes "..."]
    python scripts/create_pilot.py --list
    python scripts/create_pilot.py --activate <pilot_id>
    python scripts/create_pilot.py --complete <pilot_id>

Opciones:
    --sqlite    Usar SQLite en memoria (para desarrollo local sin PostgreSQL)
"""

import argparse
import asyncio
import sys
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.session import get_db_session, init_db, Base
from app.models.tenant import Tenant
from app.models.user import User
from app.models.tenant_member import TenantMember, MemberRole
from app.core.beta.models import PilotTenant, PilotStatus

# Global session factory (set by init_db_with_mode)
_async_session_factory = None


async def init_db_with_mode(use_sqlite: bool = False):
    """Inicializa DB con SQLite en memoria o PostgreSQL según flag."""
    global _async_session_factory
    
    if use_sqlite:
        # SQLite en memoria para desarrollo
        # Usar archivo SQLite para compartir entre scripts
        db_path = "sqlite+aiosqlite:///./test_beta.db"
        engine = create_async_engine(
            db_path,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    else:
        # PostgreSQL (producción)
        await init_db()
        _async_session_factory = get_db_session


def get_session() -> AsyncSession:
    if _async_session_factory is None:
        raise RuntimeError("DB no inicializada. Llamar init_db_with_mode() primero.")
    return _async_session_factory()


async def get_admin_user(session: AsyncSession, tenant_id: UUID) -> User | None:
    """Obtiene el owner/admin del tenant para invited_by_id."""
    result = await session.execute(
        select(User)
        .join(TenantMember, User.id == TenantMember.user_id)
        .where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.role.in_([MemberRole.OWNER, MemberRole.ADMIN]),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_pilot(tenant_id: str, admin_email: str | None, notes: str | None) -> None:
    async with get_session() as session:
        # Verificar tenant existe
        tenant_uuid = UUID(tenant_id)
        result = await session.execute(select(Tenant).where(Tenant.id == tenant_uuid))
        tenant = result.scalar_one_or_none()
        if not tenant:
            print(f"❌ Tenant {tenant_id} no encontrado")
            sys.exit(1)

        # Verificar si ya es piloto
        result = await session.execute(select(PilotTenant).where(PilotTenant.tenant_id == tenant_uuid))
        existing = result.scalar_one_or_none()
        if existing:
            print(f"⚠️  Tenant ya es piloto: {existing.id} (status: {existing.status.value})")
            return

        # Buscar admin para invited_by_id
        invited_by = None
        if admin_email:
            result = await session.execute(select(User).where(User.email == admin_email))
            invited_by = result.scalar_one_or_none()
        else:
            invited_by = await get_admin_user(session, tenant_uuid)

        pilot = PilotTenant(
            tenant_id=tenant_uuid,
            status=PilotStatus.PENDING,
            invited_by_id=invited_by.id if invited_by else None,
            notes=notes,
        )
        session.add(pilot)
        await session.commit()
        await session.refresh(pilot)

        print(f"✅ Piloto creado:")
        print(f"   ID: {pilot.id}")
        print(f"   Tenant: {tenant.name} ({tenant.id})")
        print(f"   Status: {pilot.status.value}")
        print(f"   Invited by: {invited_by.email if invited_by else 'N/A'}")
        print(f"   Notes: {notes or 'N/A'}")


async def list_pilots() -> None:
    async with get_session() as session:
        result = await session.execute(
            select(PilotTenant, Tenant.name)
            .join(Tenant, PilotTenant.tenant_id == Tenant.id)
            .order_by(PilotTenant.created_at.desc())
        )
        rows = result.all()

        if not rows:
            print("No hay pilotos registrados")
            return

        print(f"{'Pilot ID':<36} {'Tenant':<30} {'Status':<12} {'Onboarded':<20} {'Notes'}")
        print("-" * 120)
        for pilot, tenant_name in rows:
            onboarded = pilot.onboarded_at.strftime("%Y-%m-%d %H:%M") if pilot.onboarded_at else "—"
            notes = (pilot.notes[:40] + "...") if pilot.notes and len(pilot.notes) > 40 else (pilot.notes or "—")
            print(f"{str(pilot.id):<36} {tenant_name:<30} {pilot.status.value:<12} {onboarded:<20} {notes}")


async def activate_pilot(pilot_id: str) -> None:
    async with get_session() as session:
        result = await session.execute(select(PilotTenant).where(PilotTenant.id == UUID(pilot_id)))
        pilot = result.scalar_one_or_none()
        if not pilot:
            print(f"[ERROR] Piloto {pilot_id} no encontrado")
            sys.exit(1)

        pilot.status = PilotStatus.ACTIVE
        pilot.onboarded_at = __import__('datetime').datetime.now(__import__('datetime').UTC)
        await session.commit()
        print(f"[OK] Piloto activado: {pilot.id} (tenant: {pilot.tenant_id})")


async def complete_pilot(pilot_id: str) -> None:
    async with get_session() as session:
        result = await session.execute(select(PilotTenant).where(PilotTenant.id == UUID(pilot_id)))
        pilot = result.scalar_one_or_none()
        if not pilot:
            print(f"[ERROR] Piloto {pilot_id} no encontrado")
            sys.exit(1)

        pilot.status = PilotStatus.COMPLETED
        pilot.completed_at = __import__('datetime').datetime.now(__import__('datetime').UTC)
        await session.commit()
        print(f"[OK] Piloto completado: {pilot.id}")


async def main():
    parser = argparse.ArgumentParser(description="Gestionar pilotos beta")
    parser.add_argument("--sqlite", action="store_true", help="Usar SQLite en memoria (dev)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    create_parser = subparsers.add_parser("create", help="Crear piloto")
    create_parser.add_argument("tenant_id", help="UUID del tenant")
    create_parser.add_argument("--email", help="Email del admin que invita (opcional)")
    create_parser.add_argument("--notes", help="Notas del piloto (opcional)")

    # list
    subparsers.add_parser("list", help="Listar pilotos")

    # activate
    activate_parser = subparsers.add_parser("activate", help="Marcar piloto como activo (onboarded)")
    activate_parser.add_argument("pilot_id", help="UUID del piloto")

    # complete
    complete_parser = subparsers.add_parser("complete", help="Marcar piloto como completado")
    complete_parser.add_argument("pilot_id", help="UUID del piloto")

    args = parser.parse_args()

    # Init DB
    await init_db_with_mode(use_sqlite=args.sqlite)

    if args.command == "create":
        await create_pilot(args.tenant_id, args.email, args.notes)
    elif args.command == "list":
        await list_pilots()
    elif args.command == "activate":
        await activate_pilot(args.pilot_id)
    elif args.command == "complete":
        await complete_pilot(args.pilot_id)


if __name__ == "__main__":
    asyncio.run(main())