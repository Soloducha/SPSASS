"""0003_enable_rls

Revision ID: 20260920_1500_0003
Revises: 20260920_1430_0002
Create Date: 2026-09-20 15:00:00.000000

Habilita Row Level Security (RLS) en todas las tablas de negocio multi-tenant.
Crea rol app_user y políticas de aislamiento por tenant_id.
Idempotente: seguro re-ejecutar.
No rompe migración 0001 (hypertable metrics incluida).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260920_1500_0003'
down_revision: Union[str, None] = '20260920_1430_0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tablas de negocio que llevan tenant_id (excluye 'tenants' que es la tabla raíz)
BUSINESS_TABLES = [
    'users',
    'tenant_members',
    'servers',
    'metrics',
    'services',
    'processes',
    'jobs',
    'job_runs',
    'alert_rules',
    'alerts',
    'alert_deliveries',
    'reports',
    'api_keys',
]


def upgrade() -> None:
    # ──────────────────────────────────────────────
    # 1. Crear rol de aplicación si no existe
    # ──────────────────────────────────────────────
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
                CREATE ROLE app_user NOINHERIT;
            END IF;
        END
        $$;
    """)

    # ──────────────────────────────────────────────
    # 2. Función auxiliar para obtener tenant_id del contexto
    # ──────────────────────────────────────────────
    # current_setting('app.tenant_id', true) retorna NULL si no está seteado
    # El 'true' hace que no falle si la variable no existe
    op.execute("""
        CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS uuid
        LANGUAGE sql STABLE PARALLEL SAFE
        AS $$
            SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
        $$;
    """)

    # ──────────────────────────────────────────────
    # 3. Habilitar RLS y crear políticas en cada tabla de negocio
    # ──────────────────────────────────────────────
    # En modo offline (--sql) no hay bind, así que aplicamos a todas las tablas conocidas.
    # Las tablas que no existan simplemente fallarán en runtime (lo cual es correcto).
    for table in BUSINESS_TABLES:
        # Habilitar RLS (idempotente: ALTER TABLE ... ENABLE ROW LEVEL SECURITY es safe)
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')

        # Forzar RLS para dueños de tabla (superusers bypass por defecto; esto lo evita)
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;')

        # Política SELECT: solo filas del tenant actual
        op.execute(f"""
            DROP POLICY IF EXISTS "tenant_isolation_select" ON "{table}";
            CREATE POLICY "tenant_isolation_select" ON "{table}"
                FOR SELECT
                TO app_user
                USING (tenant_id = current_tenant_id());
        """)

        # Política INSERT: solo insertar con tenant_id = tenant actual
        op.execute(f"""
            DROP POLICY IF EXISTS "tenant_isolation_insert" ON "{table}";
            CREATE POLICY "tenant_isolation_insert" ON "{table}"
                FOR INSERT
                TO app_user
                WITH CHECK (tenant_id = current_tenant_id());
        """)

        # Política UPDATE: solo actualizar filas del tenant actual
        op.execute(f"""
            DROP POLICY IF EXISTS "tenant_isolation_update" ON "{table}";
            CREATE POLICY "tenant_isolation_update" ON "{table}"
                FOR UPDATE
                TO app_user
                USING (tenant_id = current_tenant_id())
                WITH CHECK (tenant_id = current_tenant_id());
        """)

        # Política DELETE: solo borrar filas del tenant actual
        op.execute(f"""
            DROP POLICY IF EXISTS "tenant_isolation_delete" ON "{table}";
            CREATE POLICY "tenant_isolation_delete" ON "{table}"
                FOR DELETE
                TO app_user
                USING (tenant_id = current_tenant_id());
        """)

        # Otorgar permisos al rol app_user
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO app_user;')

    # ──────────────────────────────────────────────
    # 4. Tabla 'tenants': política especial
    #    - SELECT: solo su propia fila (para que tenant vea su info)
    #    - INSERT/UPDATE/DELETE: solo superusers (via bypass), app_user no toca tenants
    # ──────────────────────────────────────────────
    op.execute('ALTER TABLE "tenants" ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE "tenants" FORCE ROW LEVEL SECURITY;')

    op.execute("""
        DROP POLICY IF EXISTS "tenant_isolation_select" ON "tenants";
        CREATE POLICY "tenant_isolation_select" ON "tenants"
            FOR SELECT
            TO app_user
            USING (id = current_tenant_id());
    """)

    # app_user NO tiene INSERT/UPDATE/DELETE en tenants (solo admins via service role)
    op.execute('GRANT SELECT ON "tenants" TO app_user;')

    # ──────────────────────────────────────────────
    # 5. Secuencias/grants para UUID generation (gen_random_uuid)
    # ──────────────────────────────────────────────
    op.execute("GRANT USAGE ON SCHEMA public TO app_user;")
    op.execute("GRANT EXECUTE ON FUNCTION gen_random_uuid() TO app_user;")


def downgrade() -> None:
    # ──────────────────────────────────────────────
    # Revertir: quitar políticas, deshabilitar RLS, revocar grants
    # ──────────────────────────────────────────────
    for table in BUSINESS_TABLES + ['tenants']:
        op.execute(f'DROP POLICY IF EXISTS "tenant_isolation_select" ON "{table}";')
        op.execute(f'DROP POLICY IF EXISTS "tenant_isolation_insert" ON "{table}";')
        op.execute(f'DROP POLICY IF EXISTS "tenant_isolation_update" ON "{table}";')
        op.execute(f'DROP POLICY IF EXISTS "tenant_isolation_delete" ON "{table}";')
        op.execute(f'ALTER TABLE IF EXISTS "{table}" DISABLE ROW LEVEL SECURITY;')
        op.execute(f'REVOKE ALL ON "{table}" FROM app_user;')

    # Quitar función auxiliar
    op.execute("DROP FUNCTION IF EXISTS current_tenant_id();")

    # Quitar rol (solo si no tiene objetos dependientes)
    op.execute("DROP ROLE IF EXISTS app_user;")