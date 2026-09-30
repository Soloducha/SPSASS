"""process_last_count

Revision ID: 20260928_0001_0008
Revises: 20260928_0000_0007_alert_rule_id_nullable
Create Date: 2026-09-28 00:00:00.000000

Añade columnas last_count y last_checked_at a la tabla processes
para almacenar el estado derivado del agente.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260928_0001_0008'
down_revision: Union[str, None] = '20260928_0000_0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────────────────────────────
    # Add last_count and last_checked_at to processes
    # ──────────────────────────────────────────────
    op.add_column(
        'processes',
        sa.Column('last_count', sa.Integer(), nullable=False, server_default='0')
    )
    op.add_column(
        'processes',
        sa.Column('last_checked_at', postgresql.TIMESTAMP(timezone=True), nullable=True)
    )


def downgrade() -> None:
    # ──────────────────────────────────────────────
    # Revert: drop columns from processes
    # ──────────────────────────────────────────────
    op.drop_column('processes', 'last_checked_at')
    op.drop_column('processes', 'last_count')