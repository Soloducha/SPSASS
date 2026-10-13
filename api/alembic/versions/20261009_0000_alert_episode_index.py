"""alert_episode_index

Revision ID: 20261009_0000
Revises: 0ad7e623e42b
Create Date: 2026-10-09 00:00:00.000000

Añade índices compuestos para optimizar el gate de deduplicación de episodios
(_get_episode_alert). La consulta filtra por rule_id + target_entity_id (o
server_id) + status + silenced_at IS NOT NULL. Los índices compuestos evitan
escaneos secuenciales cuando hay muchas alertas por tenant.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20261009_0000'
down_revision: Union[str, None] = '0ad7e623e42b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────────────────────────────
    # Composite index for primary episode gate path (SERVICE/PROCESS/JOB)
    # Query: rule_id + target_entity_id + status + silenced_at IS NOT NULL
    # ──────────────────────────────────────────────
    op.create_index(
        'ix_alerts_episode_gate_target',
        'alerts',
        ['rule_id', 'target_entity_id', 'status', 'silenced_at'],
        postgresql_where=sa.text("status IN ('open', 'acknowledged', 'resolved')"),
    )

    # ──────────────────────────────────────────────
    # Composite index for legacy SERVER fallback path
    # Query: rule_id + server_id + status + silenced_at IS NOT NULL
    # ──────────────────────────────────────────────
    op.create_index(
        'ix_alerts_episode_gate_server',
        'alerts',
        ['rule_id', 'server_id', 'status', 'silenced_at'],
        postgresql_where=sa.text("status IN ('open', 'acknowledged', 'resolved')"),
    )


def downgrade() -> None:
    # ──────────────────────────────────────────────
    # Drop composite indexes
    # ──────────────────────────────────────────────
    op.drop_index('ix_alerts_episode_gate_target', table_name='alerts')
    op.drop_index('ix_alerts_episode_gate_server', table_name='alerts')