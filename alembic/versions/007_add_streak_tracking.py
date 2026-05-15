"""Add daily streak tracking columns to users table

Revision ID: 007
Revises: 006
Create Date: 2026-03-06
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("streak_count", sa.Integer(), server_default=sa.text("0"), nullable=False)
    )
    op.add_column(
        "users",
        sa.Column("last_streak_claim_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_users_streak_count", "users", ["streak_count"])
    op.create_index("ix_users_last_streak_claim_at", "users", ["last_streak_claim_at"])


def downgrade():
    op.drop_index("ix_users_last_streak_claim_at", table_name="users")
    op.drop_index("ix_users_streak_count", table_name="users")
    op.drop_column("users", "last_streak_claim_at")
    op.drop_column("users", "streak_count")
