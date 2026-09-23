#!/usr/bin/env python
"""Script de bootstrap: crea el primer tenant + admin desde variables de entorno.

Uso:
    SPSAAS_ADMIN_EMAIL=admin@example.com SPSAAS_ADMIN_PASSWORD=securepass python -m scripts.seed_admin

Variables de entorno requeridas:
    SPSAAS_ADMIN_EMAIL    - Email del admin inicial
    SPSAAS_ADMIN_PASSWORD - Contraseña del admin (mín 8 chars)
    SPSAAS_ADMIN_TENANT_SLUG - (opcional) Slug del tenant, default: "spsaas"
    SPSAAS_ADMIN_TENANT_NAME - (opcional) Nombre del tenant, default: "SPSAAS"
    SPSAAS_ADMIN_FULL_NAME  - (opcional) Nombre completo del admin

NO dejes credenciales hardcodeadas ni por defecto inseguras.
"""

import os
import sys
from pathlib import Path

from sqlalchemy import select

# Asegurar que app está en el path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.auth.security import hash_password
from app.core.config import get_settings
from app.db.session import close_db, get_db_session, init_db
from app.models.tenant import PlanType, Tenant
from app.models.tenant_member import MemberRole, TenantMember
from app.models.user import User, UserRole


async def seed_admin() -> None:
    """Crea tenant y admin inicial si no existen."""
    _ = get_settings()

    # Validar variables de entorno requeridas
    admin_email = os.getenv("SPSAAS_ADMIN_EMAIL")
    admin_password = os.getenv("SPSAAS_ADMIN_PASSWORD")

    if not admin_email:
        print("ERROR: SPSAAS_ADMIN_EMAIL no está configurada", file=sys.stderr)
        sys.exit(1)

    if not admin_password:
        print("ERROR: SPSAAS_ADMIN_PASSWORD no está configurada", file=sys.stderr)
        sys.exit(1)

    if len(admin_password) < 8:
        print("ERROR: SPSAAS_ADMIN_PASSWORD debe tener al menos 8 caracteres", file=sys.stderr)
        sys.exit(1)

    # Opcionales
    tenant_slug = os.getenv("SPSAAS_ADMIN_TENANT_SLUG", "spsaas")
    tenant_name = os.getenv("SPSAAS_ADMIN_TENANT_NAME", "SPSAAS")
    admin_full_name = os.getenv("SPSAAS_ADMIN_FULL_NAME", "Admin")

    print(f"Inicializando tenant: {tenant_name} ({tenant_slug})")
    print(f"Creando admin: {admin_email}")

    async with get_db_session() as session:
        # Verificar si ya existe el tenant
        result = await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        tenant = result.scalar_one_or_none()

        if tenant:
            print(f"Tenant '{tenant_slug}' ya existe (id={tenant.id})")
        else:
            tenant = Tenant(name=tenant_name, slug=tenant_slug, plan=PlanType.ENTERPRISE)
            session.add(tenant)
            await session.flush()
            print(f"Tenant creado: id={tenant.id}")

        # Verificar si ya existe el usuario
        result = await session.execute(select(User).where(User.email == admin_email))
        user = result.scalar_one_or_none()

        if user:
            print(f"Usuario '{admin_email}' ya existe (id={user.id})")
            # Asegurar que sea superuser y owner
            user.is_superuser = True
            user.role = UserRole.OWNER
            user.is_active = True
            user.password_hash = hash_password(admin_password)
            if admin_full_name:
                user.full_name = admin_full_name
        else:
            user = User(
                email=admin_email,
                password_hash=hash_password(admin_password),
                tenant_id=tenant.id,
                full_name=admin_full_name,
                role=UserRole.OWNER,
                is_active=True,
                is_superuser=True,
            )
            session.add(user)
            await session.flush()
            print(f"Usuario creado: id={user.id}")

        # Verificar/crear tenant_members
        result = await session.execute(
            select(TenantMember).where(
                TenantMember.user_id == user.id,
                TenantMember.tenant_id == tenant.id,
            )
        )
        member = result.scalar_one_or_none()

        if member:
            member.role = MemberRole.OWNER
            print("Membresía actualizada a OWNER")
        else:
            member = TenantMember(user_id=user.id, tenant_id=tenant.id, role=MemberRole.OWNER)
            session.add(member)
            print("Membresía creada: OWNER")

        await session.commit()

    print("\n✅ Bootstrap completado exitosamente")
    print(f"   Tenant: {tenant_name} ({tenant_slug})")
    print(f"   Admin:  {admin_email}")
    print("   Superuser: True")
    print("\nAhora puedes loguearte en /auth/login")


async def main() -> None:
    """Inicializa BD y ejecuta el seed en un único event loop."""
    await init_db()
    try:
        await seed_admin()
    finally:
        await close_db()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

