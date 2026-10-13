"""add_tenant_invitations_table

Revision ID: 20261013_0000
Revises: 20261009_0000
Create Date: 2026-10-13 00:00:00.000000

Añade la tabla `tenant_invitations` para el flujo de invitaciones a tenant (T2 - Mes 6).

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20261013_0000'
down_revision: Union[str, None] = '20261009_0000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # member_role enum ya existe desde 0001_initial (create_type=False)
    member_role = postgresql.ENUM(
        'owner', 'admin', 'member', 'viewer',
        name='member_role',
        create_type=False
    )

    op.create_table(
        'tenant_invitations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('role', member_role, nullable=False, server_default='member'),
        sa.Column('token', sa.String(1024), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('invited_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE', name='fk_tenant_invitations_tenant_id'),
        sa.ForeignKeyConstraint(['invited_by_id'], ['users.id'], ondelete='SET NULL', name='fk_tenant_invitations_invited_by_id'),
        sa.PrimaryKeyConstraint('id', name='pk_tenant_invitations'),
    )
    op.create_index('ix_tenant_invitations_tenant_id', 'tenant_invitations', ['tenant_id'])
    op.create_index('ix_tenant_invitations_email', 'tenant_invitations', ['email'])
    op.create_index('ix_tenant_invitations_token', 'tenant_invitations', ['token'], unique=True)
    # Índice parcial único: solo una invitación *pendiente* por (tenant, email)
    op.create_index(
        'uq_tenant_invitation_pending',
        'tenant_invitations',
        ['tenant_id', 'email'],
        unique=True,
        postgresql_where=sa.text('accepted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_tenant_invitation_pending', table_name='tenant_invitations')
    op.drop_index('ix_tenant_invitations_token', table_name='tenant_invitations')
    op.drop_index('ix_tenant_invitations_email', table_name='tenant_invitations')
    op.drop_index('ix_tenant_invitations_tenant_id', table_name='tenant_invitations')
    op.drop_table('tenant_invitations')