"""alert_delivery_config

Revision ID: 20260928_0003_0010
Revises: 20260928_0002_0009
Create Date: 2026-09-28 00:00:00.000000

Añade columna config a alert_deliveries para snapshot de configuración
de canal en tiempo de creación. Esto permite que entregas sin regla
(job-failure alerts) se despachen sin depender de alert.rule.channels.
Para filas legacy (config=NULL), delivery_runner hace fallback a rule.channels.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260928_0003_0010'
down_revision: Union[str, None] = '20260928_0002_0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────────────────────────────
    # Add config column to alert_deliveries
    # ──────────────────────────────────────────────
    op.add_column(
        'alert_deliveries',
        sa.Column('config', sa.JSON, nullable=True)
    )


def downgrade() -> None:
    # ──────────────────────────────────────────────
    # Revert: drop config column from alert_deliveries
    # ──────────────────────────────────────────────
    op.drop_column('alert_deliveries', 'config')