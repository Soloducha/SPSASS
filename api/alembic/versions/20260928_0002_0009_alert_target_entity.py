"""alert_target_entity

Revision ID: 20260928_0002_0009
Revises: 20260928_0001_0008
Create Date: 2026-09-28 00:00:00.000000

Añade columna target_entity_id a la tabla alerts para idempotencia
y resolución unívoca de alertas de SERVICE/PROCESS/JOB por entidad objetivo.
Para SERVER, se setea a rule.entity_id cuando está presente.
Mantenido nullable para compatibilidad con alertas de job-runner (rule_id=None).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260928_0002_0009'
down_revision: Union[str, None] = '20260928_0001_0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────────────────────────────
    # Add target_entity_id to alerts
    # ──────────────────────────────────────────────
    op.add_column(
        'alerts',
        sa.Column('target_entity_id', postgresql.UUID(as_uuid=True), nullable=True, index=True)
    )


def downgrade() -> None:
    # ──────────────────────────────────────────────
    # Revert: drop column from alerts
    # ──────────────────────────────────────────────
    op.drop_column('alerts', 'target_entity_id')