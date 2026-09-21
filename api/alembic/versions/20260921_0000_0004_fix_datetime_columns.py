"""fix_datetime_columns

Revision ID: 20260921_0000_0004
Revises: 20260920_1500_0003
Create Date: 2026-09-21 00:00:00.000000

Corrige el tipo de columna api_keys.last_used_at de VARCHAR a TIMESTAMP WITH TIME ZONE
para coincidir con el modelo ORM y permitir datetimes timezone-aware desde asyncpg.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260921_0000_0004'
down_revision: Union[str, None] = '20260920_1500_0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────────────────────────────
    # Alter api_keys.last_used_at from VARCHAR(50) to TIMESTAMP WITH TIME ZONE
    # ──────────────────────────────────────────────
    op.alter_column(
        'api_keys',
        'last_used_at',
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_type=sa.String(50),
        nullable=True,
        postgresql_using='last_used_at::timestamp with time zone',
    )


def downgrade() -> None:
    # ──────────────────────────────────────────────
    # Revert api_keys.last_used_at from TIMESTAMP WITH TIME ZONE to VARCHAR(50)
    # ──────────────────────────────────────────────
    op.alter_column(
        'api_keys',
        'last_used_at',
        type_=sa.String(50),
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=True,
        postgresql_using='last_used_at::text',
    )