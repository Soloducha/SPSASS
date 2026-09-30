"""alert_rule_id_nullable

Revision ID: 20260928_0000_0007
Revises: 20260923_2000_0006
Create Date: 2026-09-28 00:00:00.000000

Hace nullable el campo alerts.rule_id para permitir alertas de job failure
sin una AlertRule asociada (job.alert_on_fail=True). El campo value_at_trigger
se mantiene NOT NULL (se setea a float(exit_code or 0.0) en job runner).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260928_0000_0007'
down_revision: Union[str, None] = '20260923_2000_0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────────────────────────────
    # Alter alerts.rule_id from NOT NULL to NULLABLE
    # ──────────────────────────────────────────────
    op.alter_column(
        'alerts',
        'rule_id',
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    # ──────────────────────────────────────────────
    # Revert alerts.rule_id to NOT NULL
    # ⚠️ WARNING: This will fail if there are existing NULL rule_id rows.
    # If downgrading after job failure alerts were created, either:
    #   a) Delete/fix those rows first, or
    #   b) Accept that the downgrade will fail on constraint violation.
    # ──────────────────────────────────────────────
    op.alter_column(
        'alerts',
        'rule_id',
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )