"""Add multi-device push tokens and Expo receipt tracking

Revision ID: 006
Revises: 005
Create Date: 2026-03-05
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "push_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expo_push_token", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), server_default=sa.text("'expo'"), nullable=False),
        sa.Column("platform", sa.String(), nullable=True),
        sa.Column("device_id", sa.String(), nullable=True),
        sa.Column("app_version", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("invalidated_reason", sa.String(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("expo_push_token", name="uq_push_devices_expo_push_token"),
    )
    op.create_index("ix_push_devices_user_id", "push_devices", ["user_id"])
    op.create_index("ix_push_devices_provider", "push_devices", ["provider"])
    op.create_index("ix_push_devices_device_id", "push_devices", ["device_id"])
    op.create_index("ix_push_devices_is_active", "push_devices", ["is_active"])
    op.create_index("ix_push_devices_last_seen_at", "push_devices", ["last_seen_at"])
    op.create_index("ix_push_devices_expo_push_token", "push_devices", ["expo_push_token"], unique=True)

    op.create_table(
        "expo_push_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), server_default=sa.text("'transactional'"), nullable=False),
        sa.Column("status", sa.String(), server_default=sa.text("'sent'"), nullable=False),
        sa.Column("expo_push_token", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("push_device_id", sa.Integer(), nullable=True),
        sa.Column("notification_id", sa.Integer(), nullable=True),
        sa.Column("admin_log_id", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["push_device_id"], ["push_devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["admin_log_id"], ["push_notification_logs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("ticket_id", name="uq_expo_push_receipts_ticket_id"),
    )
    op.create_index("ix_expo_push_receipts_ticket_id", "expo_push_receipts", ["ticket_id"], unique=True)
    op.create_index("ix_expo_push_receipts_status", "expo_push_receipts", ["status"])
    op.create_index("ix_expo_push_receipts_source_type", "expo_push_receipts", ["source_type"])
    op.create_index("ix_expo_push_receipts_user_id", "expo_push_receipts", ["user_id"])
    op.create_index("ix_expo_push_receipts_push_device_id", "expo_push_receipts", ["push_device_id"])
    op.create_index("ix_expo_push_receipts_notification_id", "expo_push_receipts", ["notification_id"])
    op.create_index("ix_expo_push_receipts_admin_log_id", "expo_push_receipts", ["admin_log_id"])
    op.create_index("ix_expo_push_receipts_expo_push_token", "expo_push_receipts", ["expo_push_token"])
    op.create_index("ix_expo_push_receipts_created_at", "expo_push_receipts", ["created_at"])


def downgrade():
    op.drop_index("ix_expo_push_receipts_created_at", table_name="expo_push_receipts")
    op.drop_index("ix_expo_push_receipts_expo_push_token", table_name="expo_push_receipts")
    op.drop_index("ix_expo_push_receipts_admin_log_id", table_name="expo_push_receipts")
    op.drop_index("ix_expo_push_receipts_notification_id", table_name="expo_push_receipts")
    op.drop_index("ix_expo_push_receipts_push_device_id", table_name="expo_push_receipts")
    op.drop_index("ix_expo_push_receipts_user_id", table_name="expo_push_receipts")
    op.drop_index("ix_expo_push_receipts_source_type", table_name="expo_push_receipts")
    op.drop_index("ix_expo_push_receipts_status", table_name="expo_push_receipts")
    op.drop_index("ix_expo_push_receipts_ticket_id", table_name="expo_push_receipts")
    op.drop_table("expo_push_receipts")

    op.drop_index("ix_push_devices_expo_push_token", table_name="push_devices")
    op.drop_index("ix_push_devices_last_seen_at", table_name="push_devices")
    op.drop_index("ix_push_devices_is_active", table_name="push_devices")
    op.drop_index("ix_push_devices_device_id", table_name="push_devices")
    op.drop_index("ix_push_devices_provider", table_name="push_devices")
    op.drop_index("ix_push_devices_user_id", table_name="push_devices")
    op.drop_table("push_devices")
