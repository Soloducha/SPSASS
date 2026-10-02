"""agent_commands

Revision ID: 20261002_0000_0012
Revises: 20260930_0011
Create Date: 2026-10-02 00:00:00.000000

Tabla para comandos pendientes del agente (auto-restart de servicios/procesos).
El worker encola comandos; el agente hace polling y ejecuta localmente.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20261002_0000_0012'
down_revision: Union[str, None] = '20260930_0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────────────────────────────
    # agent_commands table
    # ──────────────────────────────────────────────
    op.create_table(
        'agent_commands',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('server_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_type', sa.String(20), nullable=False),  # 'service' | 'process'
        sa.Column('entity_name', sa.String(255), nullable=False),
        sa.Column('command', sa.String(500), nullable=True),  # override opcional
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('backoff_s', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('output_tail', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_agent_commands_server_status', 'agent_commands', ['server_id', 'status'])
    op.create_index('ix_agent_commands_tenant_server', 'agent_commands', ['tenant_id', 'server_id'])


def downgrade() -> None:
    # ──────────────────────────────────────────────
    # Revert: drop agent_commands table
    # ──────────────────────────────────────────────
    op.drop_index('ix_agent_commands_tenant_server', table_name='agent_commands')
    op.drop_index('ix_agent_commands_server_status', table_name='agent_commands')
    op.drop_table('agent_commands')