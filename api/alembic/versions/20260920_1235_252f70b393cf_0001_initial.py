"""0001_initial

Revision ID: 252f70b393cf
Revises: 
Create Date: 2026-09-20 12:35:50.997274

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '252f70b393cf'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────────────────────────────
    # Enums
    # ──────────────────────────────────────────────
    plan_type = postgresql.ENUM('free', 'starter', 'growth', 'enterprise', name='plan_type', create_type=False)
    plan_type.create(op.get_bind(), checkfirst=True)

    user_role = postgresql.ENUM('owner', 'admin', 'member', 'viewer', name='user_role', create_type=False)
    user_role.create(op.get_bind(), checkfirst=True)

    member_role = postgresql.ENUM('owner', 'admin', 'member', 'viewer', name='member_role', create_type=False)
    member_role.create(op.get_bind(), checkfirst=True)

    server_status = postgresql.ENUM('online', 'offline', 'degraded', 'unknown', name='server_status', create_type=False)
    server_status.create(op.get_bind(), checkfirst=True)

    metric_type = postgresql.ENUM('cpu_usage', 'mem_usage', 'disk_usage', 'load_avg1', 'load_avg5', 'load_avg15', name='metric_type', create_type=False)
    metric_type.create(op.get_bind(), checkfirst=True)

    service_state = postgresql.ENUM('running', 'stopped', 'failed', 'unknown', name='service_state', create_type=False)
    service_state.create(op.get_bind(), checkfirst=True)

    job_kind = postgresql.ENUM('cron', 'batch', 'scheduled', name='job_kind', create_type=False)
    job_kind.create(op.get_bind(), checkfirst=True)

    job_status = postgresql.ENUM('active', 'paused', 'disabled', name='job_status', create_type=False)
    job_status.create(op.get_bind(), checkfirst=True)

    alert_severity = postgresql.ENUM('info', 'warning', 'critical', name='alert_severity', create_type=False)
    alert_severity.create(op.get_bind(), checkfirst=True)

    alert_status = postgresql.ENUM('open', 'acknowledged', 'resolved', name='alert_status', create_type=False)
    alert_status.create(op.get_bind(), checkfirst=True)

    alert_operator = postgresql.ENUM('gt', 'gte', 'lt', 'lte', 'eq', 'neq', name='alert_operator', create_type=False)
    alert_operator.create(op.get_bind(), checkfirst=True)

    entity_type = postgresql.ENUM('server', 'service', 'process', 'job', 'metric', name='entity_type', create_type=False)
    entity_type.create(op.get_bind(), checkfirst=True)

    report_type = postgresql.ENUM('availability', 'incidents', 'alerts', 'sla', 'metrics', name='report_type', create_type=False)
    report_type.create(op.get_bind(), checkfirst=True)

    report_status = postgresql.ENUM('pending', 'generating', 'completed', 'failed', name='report_status', create_type=False)
    report_status.create(op.get_bind(), checkfirst=True)

    # ──────────────────────────────────────────────
    # Tables
    # ──────────────────────────────────────────────

    # tenants
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('plan', plan_type, nullable=False, server_default='free'),
        sa.Column('settings', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_tenants'),
        sa.UniqueConstraint('slug', name='uq_tenants_slug'),
    )
    op.create_index('ix_tenants_slug', 'tenants', ['slug'], unique=True)

    # users
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', user_role, nullable=False, server_default='member'),
        sa.Column('full_name', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('settings', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_users'),
        sa.UniqueConstraint('email', name='uq_users_email'),
    )
    op.create_index('ix_users_tenant_id', 'users', ['tenant_id'])
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # tenant_members
    op.create_table(
        'tenant_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', member_role, nullable=False, server_default='member'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_tenant_members'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_tenant_members_tenant_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='fk_tenant_members_user_id'),
        sa.UniqueConstraint('user_id', 'tenant_id', name='uq_tenant_member_user_tenant'),
    )
    op.create_index('ix_tenant_members_user_id', 'tenant_members', ['user_id'])
    op.create_index('ix_tenant_members_tenant_id', 'tenant_members', ['tenant_id'])

    # servers
    op.create_table(
        'servers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('hostname', sa.String(255), nullable=False),
        sa.Column('ip', sa.String(45), nullable=True),
        sa.Column('os', sa.String(100), nullable=True),
        sa.Column('agent_version', sa.String(50), nullable=True),
        sa.Column('status', server_status, nullable=False, server_default='unknown'),
        sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('alert_channels', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_servers'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_servers_tenant_id'),
    )
    op.create_index('ix_servers_tenant_id', 'servers', ['tenant_id'])

    # metrics (TimescaleDB hypertable)
    op.create_table(
        'metrics',
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('server_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', metric_type, nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('tags', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.PrimaryKeyConstraint('ts', 'server_id', name='pk_metrics'),
        sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ondelete='CASCADE', name='fk_metrics_server_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_metrics_tenant_id'),
    )
    op.create_index('ix_metrics_server_id_ts', 'metrics', ['server_id', 'ts'])
    op.create_index('ix_metrics_tenant_id_ts', 'metrics', ['tenant_id', 'ts'])
    op.create_index('ix_metrics_type_ts', 'metrics', ['type', 'ts'])

    # Convert metrics to TimescaleDB hypertable
    op.execute("SELECT create_hypertable('metrics', 'ts', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);")
    op.execute("ALTER TABLE metrics SET (timescaledb.compress, timescaledb.compress_segmentby = 'server_id, type');")
    op.execute("SELECT add_compression_policy('metrics', INTERVAL '7 days', if_not_exists => TRUE);")

    # services
    op.create_table(
        'services',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('server_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('desired_state', service_state, nullable=False, server_default='running'),
        sa.Column('auto_restart', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('last_status', service_state, nullable=False, server_default='unknown'),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('config', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_services'),
        sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ondelete='CASCADE', name='fk_services_server_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_services_tenant_id'),
    )
    op.create_index('ix_services_tenant_id', 'services', ['tenant_id'])
    op.create_index('ix_services_server_id', 'services', ['server_id'])

    # processes
    op.create_table(
        'processes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('server_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('pattern', sa.String(500), nullable=False),
        sa.Column('expected_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('auto_restart', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('config', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_processes'),
        sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ondelete='CASCADE', name='fk_processes_server_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_processes_tenant_id'),
    )
    op.create_index('ix_processes_tenant_id', 'processes', ['tenant_id'])
    op.create_index('ix_processes_server_id', 'processes', ['server_id'])

    # jobs
    op.create_table(
        'jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('server_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('kind', job_kind, nullable=False),
        sa.Column('schedule_cron', sa.String(100), nullable=True),
        sa.Column('command', sa.Text(), nullable=False),
        sa.Column('timeout_s', sa.Integer(), nullable=False, server_default='3600'),
        sa.Column('alert_on_fail', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('auto_restart', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('status', job_status, nullable=False, server_default='active'),
        sa.Column('config', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_jobs'),
        sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ondelete='CASCADE', name='fk_jobs_server_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_jobs_tenant_id'),
    )
    op.create_index('ix_jobs_tenant_id', 'jobs', ['tenant_id'])
    op.create_index('ix_jobs_server_id', 'jobs', ['server_id'])

    # job_runs
    op.create_table(
        'job_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('output_tail', sa.Text(), nullable=True),
        sa.Column('run_metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_job_runs'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE', name='fk_job_runs_job_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_job_runs_tenant_id'),
    )
    op.create_index('ix_job_runs_tenant_id', 'job_runs', ['tenant_id'])
    op.create_index('ix_job_runs_job_id', 'job_runs', ['job_id'])
    op.create_index('ix_job_runs_started_at', 'job_runs', ['started_at'])

    # alert_rules
    op.create_table(
        'alert_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_type', entity_type, nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('metric', sa.String(100), nullable=False),
        sa.Column('operator', alert_operator, nullable=False),
        sa.Column('threshold', sa.Float(), nullable=False),
        sa.Column('duration_s', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('severity', alert_severity, nullable=False, server_default='warning'),
        sa.Column('channels', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_alert_rules'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_alert_rules_tenant_id'),
    )
    op.create_index('ix_alert_rules_tenant_id', 'alert_rules', ['tenant_id'])
    op.create_index('ix_alert_rules_entity', 'alert_rules', ['entity_type', 'entity_id'])

    # alerts
    op.create_table(
        'alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('rule_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('server_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('severity', alert_severity, nullable=False),
        sa.Column('status', alert_status, nullable=False, server_default='open'),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('value_at_trigger', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_alerts'),
        sa.ForeignKeyConstraint(['rule_id'], ['alert_rules.id'], ondelete='CASCADE', name='fk_alerts_rule_id'),
        sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ondelete='SET NULL', name='fk_alerts_server_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_alerts_tenant_id'),
    )
    op.create_index('ix_alerts_tenant_id', 'alerts', ['tenant_id'])
    op.create_index('ix_alerts_rule_id', 'alerts', ['rule_id'])
    op.create_index('ix_alerts_server_id', 'alerts', ['server_id'])
    op.create_index('ix_alerts_status', 'alerts', ['status'])
    op.create_index('ix_alerts_triggered_at', 'alerts', ['triggered_at'])

    # alert_deliveries
    op.create_table(
        'alert_deliveries',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('alert_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('channel', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('external_ref', sa.String(255), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_alert_deliveries'),
        sa.ForeignKeyConstraint(['alert_id'], ['alerts.id'], ondelete='CASCADE', name='fk_alert_deliveries_alert_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_alert_deliveries_tenant_id'),
    )
    op.create_index('ix_alert_deliveries_tenant_id', 'alert_deliveries', ['tenant_id'])
    op.create_index('ix_alert_deliveries_alert_id', 'alert_deliveries', ['alert_id'])

    # reports
    op.create_table(
        'reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('type', report_type, nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', report_status, nullable=False, server_default='pending'),
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_reports'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_reports_tenant_id'),
    )
    op.create_index('ix_reports_tenant_id', 'reports', ['tenant_id'])
    op.create_index('ix_reports_period', 'reports', ['period_start', 'period_end'])
    op.create_index('ix_reports_type', 'reports', ['type'])


def downgrade() -> None:
    # Drop tables in reverse order (respecting FK constraints)
    op.drop_table('reports')
    op.drop_table('alert_deliveries')
    op.drop_table('alerts')
    op.drop_table('alert_rules')
    op.drop_table('job_runs')
    op.drop_table('jobs')
    op.drop_table('processes')
    op.drop_table('services')
    # Drop hypertable first, then table
    op.execute("SELECT drop_chunks('metrics', older_than => INTERVAL '100 years', if_exists => TRUE);")
    op.execute("DROP TABLE IF EXISTS metrics;")
    op.drop_table('servers')
    op.drop_table('tenant_members')
    op.drop_table('users')
    op.drop_table('tenants')

    # Drop enums
    for enum_name in [
        'report_status', 'report_type', 'entity_type', 'alert_operator',
        'alert_status', 'alert_severity', 'job_status', 'job_kind',
        'service_state', 'metric_type', 'server_status', 'member_role',
        'user_role', 'plan_type'
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")