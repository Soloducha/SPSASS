"""add_beta_tables

Revision ID: 0ad7e623e42b
Revises: 20261002_0000_0012
Create Date: 2026-10-08 16:53:45.375547

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0ad7e623e42b'
down_revision: Union[str, None] = '20261002_0000_0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────────────────────────────
    # pilot_tenants
    # ──────────────────────────────────────────────
    op.create_table(
        "pilot_tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "active", "inactive", "completed", "removed", name="pilot_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("invited_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_pilot_tenant_tenant_id"),
    )
    op.create_index("ix_pilot_tenants_status", "pilot_tenants", ["status"])
    op.create_index("ix_pilot_tenants_tenant_id", "pilot_tenants", ["tenant_id"])

    # ──────────────────────────────────────────────
    # pilot_feedback
    # ──────────────────────────────────────────────
    op.create_table(
        "pilot_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("pilot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_email", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("page_url", sa.String(length=500), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("screen_resolution", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="new"),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["pilot_id"], ["pilot_tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pilot_feedback_pilot_id", "pilot_feedback", ["pilot_id"])
    op.create_index("ix_pilot_feedback_user_id", "pilot_feedback", ["user_id"])
    op.create_index("ix_pilot_feedback_category", "pilot_feedback", ["category"])
    op.create_index("ix_pilot_feedback_status", "pilot_feedback", ["status"])

    # ──────────────────────────────────────────────
    # pilot_metrics_snapshots
    # ──────────────────────────────────────────────
    op.create_table(
        "pilot_metrics_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("pilot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dau", sa.Integer(), server_default="0", nullable=False),
        sa.Column("servers_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("api_keys_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("alerts_triggered", sa.Integer(), server_default="0", nullable=False),
        sa.Column("alerts_resolved", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reports_generated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("invitations_sent", sa.Integer(), server_default="0", nullable=False),
        sa.Column("invitations_accepted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("members_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_sessions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("avg_session_duration_seconds", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("features_used", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["pilot_id"], ["pilot_tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pilot_metrics_snapshots_pilot_id", "pilot_metrics_snapshots", ["pilot_id"])
    op.create_index("ix_pilot_metrics_snapshots_date", "pilot_metrics_snapshots", ["date"])
    op.create_index("ix_pilot_metrics_snapshots_pilot_date", "pilot_metrics_snapshots", ["pilot_id", "date"], unique=True)


def downgrade() -> None:
    op.drop_table("pilot_metrics_snapshots")
    op.drop_table("pilot_feedback")
    op.drop_table("pilot_tenants")
    # Drop enum type
    op.execute("DROP TYPE IF EXISTS pilot_status")