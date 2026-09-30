"""alert_silenced_at

Revision ID: 20260930_0011
Revises: 20260928_0003_0010
Create Date: 2026-09-30 00:00:00.000000

Añade columna silenced_at a alerts para marcar cuándo un operador
resolvió la alerta mientras la violación seguía viva, pidiendo no
volver a ser notificado de este episodio. NULL = nada especial.
NOT NULL = silenciado (episodio bloquea nueva alerta mientras la
violación persista; worker limpia silenced_at al auto-resolver).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260930_0011'
down_revision: Union[str, None] = '20260928_0003_0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────────────────────────────
    # Add silenced_at column to alerts
    # ──────────────────────────────────────────────
    op.add_column(
        'alerts',
        sa.Column('silenced_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    # ──────────────────────────────────────────────
    # Revert: drop silenced_at column from alerts
    # ──────────────────────────────────────────────
    op.drop_column('alerts', 'silenced_at')