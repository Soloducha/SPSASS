#!/usr/bin/env python
"""Script para crear tenant de prueba en SQLite (desarrollo local).

Uso:
    python scripts/create_test_tenant.py --sqlite [--email admin@test.com] [--password password123] [--tenant-name "Test Corp"] [--tenant-slug test-corp]

Crea en memoria:
- Tenant con plan Enterprise (sin límites)
- Admin user (superuser, owner)
- TenantMember (owner)
- PilotTenant (status=PENDING)

Imprime el tenant_id y pilot_id para usar con create_pilot.py
"""

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy import select

# Asegurar que app está en el path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.auth.security import hash_password
from app.db.session import Base
from app.models.tenant import PlanType, Tenant
from app.models.tenant_member import MemberRole, TenantMember
from app.models.user import User, UserRole
from app.core.beta.models import PilotTenant, PilotStatus


async def create_test_tenant(
    session: AsyncSession,
    email: str,
    password: str,
    tenant_name: str,
    tenant_slug: str,
    admin_full_name: str,
) -> tuple:
    """Crea tenant + admin + pilot en SQLite."""
    
    # Crear tenant
    tenant = Tenant(
        id=uuid4(),
        name=tenant_name,
        slug=tenant_slug,
        plan=PlanType.ENTERPRISE,  # Sin límites para testing
    )
    session.add(tenant)
    await session.flush()
    print(f"[OK] Tenant creado: {tenant.name} ({tenant.slug}) -- ID: {tenant.id}")

    # Crear admin user
    user = User(
        id=uuid4(),
        email=email,
        password_hash=hash_password(password),
        tenant_id=tenant.id,
        full_name=admin_full_name,
        role=UserRole.OWNER,
        is_active=True,
        is_superuser=True,
    )
    session.add(user)
    await session.flush()
    print(f"[OK] Admin creado: {email} -- ID: {user.id}")

    # Crear tenant_member
    member = TenantMember(
        id=uuid4(),
        user_id=user.id,
        tenant_id=tenant.id,
        role=MemberRole.OWNER,
    )
    session.add(member)
    print(f"[OK] Membresia: OWNER")

    # Crear piloto
    pilot = PilotTenant(
        id=uuid4(),
        tenant_id=tenant.id,
        status=PilotStatus.PENDING,
        invited_by_id=user.id,
        notes="Piloto de prueba creado via script",
    )
    session.add(pilot)
    print(f"[OK] Piloto creado: {pilot.id} -- Status: {pilot.status.value}")

    await session.commit()
    
    return tenant, user, pilot


async def main():
    parser = argparse.ArgumentParser(description="Crear tenant de prueba en SQLite")
    parser.add_argument("--sqlite", action="store_true", required=True, help="Usar SQLite en memoria (requerido)")
    parser.add_argument("--email", default="admin@test.com", help="Email del admin")
    parser.add_argument("--password", default="password123", help="Password del admin (min 8 chars)")
    parser.add_argument("--tenant-name", default="Test Corp", help="Nombre del tenant")
    parser.add_argument("--tenant-slug", default="test-corp", help="Slug del tenant")
    parser.add_argument("--admin-name", default="Admin Test", help="Nombre completo del admin")

    args = parser.parse_args()

    if not args.sqlite:
        print("ERROR: --sqlite es requerido para este script", file=sys.stderr)
        sys.exit(1)

    if len(args.password) < 8:
        print("ERROR: Password debe tener al menos 8 caracteres", file=sys.stderr)
        sys.exit(1)

    # SQLite en archivo (compartido con create_pilot.py)
    engine = create_async_engine(
        "sqlite+aiosqlite:///./test_beta.db",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with session_factory() as session:
        tenant, user, pilot = await create_test_tenant(
            session,
            email=args.email,
            password=args.password,
            tenant_name=args.tenant_name,
            tenant_slug=args.tenant_slug,
            admin_full_name=args.admin_name,
        )

    print("\n" + "="*60)
    print("RESUMEN PARA USAR EN create_pilot.py:")
    print("="*60)
    print(f"Tenant ID:  {tenant.id}")
    print(f"Pilot ID:   {pilot.id}")
    print(f"Admin:      {args.email} / {args.password}")
    print("="*60)
    print("\nProximos pasos:")
    print(f"  # El piloto ya esta creado (PENDING)")
    print(f"  python scripts/create_pilot.py --sqlite activate {pilot.id}")
    print(f"  python scripts/daily_metrics_snapshot.py --sqlite --date 2026-10-12")


if __name__ == "__main__":
    asyncio.run(main())