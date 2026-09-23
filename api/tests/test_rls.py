"""Tests de RLS (Row Level Security) contra PostgreSQL real.

La suite normal corre sobre SQLite, donde RLS no existe: la primera línea de
defensa (TenantScopedRepository + contextvars) se valida en test_multi_tenant.py.
Este archivo valida la RED DE SEGURIDAD real: las políticas de la migración 0003
filtran por `app.tenant_id` a nivel de base de datos cuando la sesión corre como
rol `app_user` (sesiones de tenant lo hacen vía `SET LOCAL ROLE app_user` en
session.py; ver odd/tasks/hardening-ci-rls.md).

Requisitos para ejecutarlo (skip si no se cumplen):
- Dialect PostgreSQL real (no SQLite).
- Migraciones aplicadas en esa BD (0023/0003 crea rol app_user + políticas;
  0006 agrega grants). En este repo: `docker compose up -d db redis` y luego
  `docker compose run --rm api alembic upgrade head`.
"""
from uuid import UUID

import pytest
import sqlalchemy as sa
from app.db.session import get_engine, get_session_factory
from app.models.server import Server, ServerStatus
from app.models.tenant import Tenant
from sqlalchemy.ext.asyncio import AsyncConnection

TENANT_A_ID = UUID("11111111-1111-1111-1111-111111111111")
TENANT_B_ID = UUID("22222222-2222-2222-2222-222222222222")


async def _role_exists(conn: AsyncConnection, role: str) -> bool:
    res = await conn.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role})
    return res.first() is not None


@pytest.mark.asyncio
async def test_rls_policy_filters_rows_by_tenant_on_postgres() -> None:
    """app_user sin contexto de tenant (o con otro tenant) no ve filas que no le pertenecen."""
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        pytest.skip("RLS real requiere PostgreSQL (las políticas viven en migraciones)")

    async with engine.connect() as conn:
        if not await _role_exists(conn, "app_user"):
            pytest.skip("migración 0003 no aplicada: rol app_user ausente")
        # app_user necesita al menos SELECT sobre servers (grants de 0003)
        grant = await conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.role_table_grants "
                "WHERE grantee = 'app_user' AND table_name = 'servers' AND privilege_type = 'SELECT'"
            )
        )
        if grant.first() is None:
            pytest.skip("migración 0003 no aplicada: app_user sin grant en servers")

    # Seed directo como superuser (bootstrap): tenants A/B + server del tenant A.
    # Commits separados: el flush conjunto de tenant+server en una sola transacción
    # no garantiza el orden de FK (SQLAlchemy/asyncpg) — por separado es determinístico.
    session_factory = get_session_factory()
    async with session_factory() as session:
        session.add(Tenant(id=TENANT_A_ID, name="Tenant A", slug="rls-tenant-a"))
        await session.commit()
    async with session_factory() as session:
        session.add(Tenant(id=TENANT_B_ID, name="Tenant B", slug="rls-tenant-b"))
        await session.commit()
    async with session_factory() as session:
        session.add(Server(hostname="rls-a.example.com", status=ServerStatus.ONLINE, tenant_id=TENANT_A_ID))
        await session.commit()

    # 1) app_user con tenant B (otro tenant) -> no ve el server de A
    async with engine.connect() as conn:
        await conn.execute(sa.text("SET LOCAL ROLE app_user"))
        await conn.execute(sa.text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(TENANT_B_ID)})
        count = await conn.execute(sa.text("SELECT count(*) FROM servers"))
        assert count.scalar_one() == 0, "RLS debe ocultar filas de otro tenant"
        await conn.rollback()  # revierte SET LOCAL

    # 2) app_user con tenant A -> ve su server
    async with engine.connect() as conn:
        await conn.execute(sa.text("SET LOCAL ROLE app_user"))
        await conn.execute(sa.text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(TENANT_A_ID)})
        count = await conn.execute(sa.text("SELECT count(*) FROM servers"))
        assert count.scalar_one() == 1, "RLS debe exponer filas del tenant propio"
        await conn.rollback()

    # 3) app_user SIN contexto de tenant -> no ve nada (current_tenant_id() es NULL)
    async with engine.connect() as conn:
        await conn.execute(sa.text("SET LOCAL ROLE app_user"))
        count = await conn.execute(sa.text("SELECT count(*) FROM servers"))
        assert count.scalar_one() == 0, "RLS debe ocultar todo sin contexto de tenant"
        await conn.rollback()
