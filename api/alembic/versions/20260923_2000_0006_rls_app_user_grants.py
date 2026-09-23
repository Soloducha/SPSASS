"""0006_rls_app_user_grants

Revision ID: 20260923_2000_0006
Revises: 20260923_0000_0005
Create Date: 2026-09-23 20:00:00.000000

Hardening RLS: habilita al rol app_user para operar las tablas que quedaron
fuera de 0003 (metrics, metric_rollups) y deja default privileges para que
migraciones futuras no requieran grants manuales.

Contexto (ver odd/tasks/hardening-ci-rls.md):
- 0003 habilitó RLS + FORCE en las tablas de negocio y creo el rol app_user.
- BUT the API runs as superuser (spsaas), and superusers bypass RLS, so the
  policies never filtered anything. The hardening makes tenant-scoped sessions
  run as app_user via `SET LOCAL ROLE app_user` (session.py T3), which means
  app_user now needs explicit grants on every table the app touches.
- `metrics` and `metric_rollups` are intentionally NOT RLS-enabled (TimescaleDB
  hypertable/columnstore limitation, documented in 0003/0005). Their tenant
  isolation stays at the application layer (TenantScopedRepository). But they
  still need DML grants so app_user can ingest/read them.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '20260923_2000_0006'
down_revision: Union[str, None] = '20260923_0000_0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tablas excluidas de RLS en 0003/0005 pero accedidas por la app como app_user.
NON_RLS_TABLES = ['metrics', 'metric_rollups']


def upgrade() -> None:
    # ──────────────────────────────────────────────
    # 1. Grants a app_user sobre tablas no-RLS que la app usa
    # ──────────────────────────────────────────────
    for table in NON_RLS_TABLES:
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO app_user;')

    # ──────────────────────────────────────────────
    # 2. Default privileges: tablas y secuencias futuras
    #    (migraciones posteriores no deberían romper a app_user por grants ausentes)
    # ──────────────────────────────────────────────
    op.execute(
        'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
        'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;'
    )
    op.execute(
        'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
        'GRANT USAGE, SELECT ON SEQUENCES TO app_user;'
    )


def downgrade() -> None:
    # ──────────────────────────────────────────────
    # Revertir: revocar grants y default privileges
    # ──────────────────────────────────────────────
    for table in NON_RLS_TABLES:
        op.execute(f'REVOKE ALL ON "{table}" FROM app_user;')

    op.execute(
        'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
        'REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM app_user;'
    )
    op.execute(
        'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
        'REVOKE USAGE, SELECT ON SEQUENCES FROM app_user;'
    )