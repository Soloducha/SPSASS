"""0005_metric_rollups

Revision ID: 20260923_0000_0005
Revises: 20260921_0000_0004
Create Date: 2026-09-23 15:30:00.000000

Crea la tabla metric_rollups con agregaciones por período (1m/5m/1h/1d).

NOTA RLS: la tabla NO se incluye en RLS a propósito (igual que 'metrics',
excluida en 0003). El worker de rollups agrega métricas de TODOS los tenants
sin contexto de tenant; las políticas FORCE TO app_user lo bloquearían.
El aislamiento de lectura se garantiza en la capa de aplicación
(TenantScopedRepository / queries con tenant_id forzado).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260923_0000_0005'
down_revision: Union[str, None] = '20260921_0000_0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────────────────────────────
    # Enum rollup_period (1m, 5m, 1h, 1d)
    # ──────────────────────────────────────────────
    rollup_period = postgresql.ENUM('1m', '5m', '1h', '1d', name='rollup_period', create_type=False)
    rollup_period.create(op.get_bind(), checkfirst=True)

    # metric_type ya existe desde 0001
    metric_type = postgresql.ENUM(
        'cpu_usage', 'mem_usage', 'disk_usage', 'load_avg1', 'load_avg5', 'load_avg15',
        name='metric_type', create_type=False,
    )

    # ──────────────────────────────────────────────
    # Tabla metric_rollups
    # ──────────────────────────────────────────────
    op.create_table(
        'metric_rollups',
        sa.Column('period', rollup_period, nullable=False),
        sa.Column('bucket_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('server_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', metric_type, nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('avg', sa.Float(), nullable=False),
        sa.Column('min', sa.Float(), nullable=False),
        sa.Column('max', sa.Float(), nullable=False),
        sa.Column('last', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('period', 'bucket_start', 'server_id', 'type', name='pk_metric_rollups'),
        sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ondelete='CASCADE', name='fk_metric_rollups_server_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_metric_rollups_tenant_id'),
    )
    op.create_index('ix_metric_rollups_tenant_period_ts', 'metric_rollups', ['tenant_id', 'period', 'bucket_start'])
    op.create_index('ix_metric_rollups_server_ts', 'metric_rollups', ['server_id', 'bucket_start'])


def downgrade() -> None:
    op.drop_index('ix_metric_rollups_server_ts', table_name='metric_rollups')
    op.drop_index('ix_metric_rollups_tenant_period_ts', table_name='metric_rollups')
    op.drop_table('metric_rollups')
    op.execute("DROP TYPE IF EXISTS rollup_period;")