"""Add scheduled push notifications

Revision ID: 013
Revises: 012
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


scheduled_status_enum = postgresql.ENUM(
    "scheduled",
    "sent",
    "failed",
    name="scheduledpushstatus",
    create_type=False,
)


def upgrade():
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE scheduledpushstatus AS ENUM ('scheduled', 'sent', 'failed'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )

    op.create_table(
        "scheduled_push_notifications",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("filters", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("scheduled_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", scheduled_status_enum, nullable=False, server_default="scheduled"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.create_index(
        "ix_scheduled_push_notifications_scheduled_time",
        "scheduled_push_notifications",
        ["scheduled_time"],
    )
    op.create_index(
        "ix_scheduled_push_notifications_status",
        "scheduled_push_notifications",
        ["status"],
    )


def downgrade():
    op.drop_index("ix_scheduled_push_notifications_status", table_name="scheduled_push_notifications")
    op.drop_index("ix_scheduled_push_notifications_scheduled_time", table_name="scheduled_push_notifications")
    op.drop_table("scheduled_push_notifications")

    scheduled_status_enum.drop(op.get_bind(), checkfirst=True)
