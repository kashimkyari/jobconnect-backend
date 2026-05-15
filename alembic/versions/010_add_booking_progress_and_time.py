"""Add booking progress statuses and start_time

Revision ID: 010
Revises: 009
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


NEW_STATUSES = [
    "booked",
    "confirmed",
    "en_route",
    "arrived",
    "in_progress",
    "done",
]

OLD_STATUSES = [
    "pending",
    "accepted",
    "rejected",
    "cancelled",
    "completed",
]

ENUM_NAME = "bookingstatus"


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for value in NEW_STATUSES:
            op.execute(f"ALTER TYPE {ENUM_NAME} ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column("bookings", sa.Column("start_time", sa.Time(), nullable=True))


def downgrade():
    op.drop_column("bookings", "start_time")

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Map new statuses to closest legacy values before enum downgrade.
    op.execute(
        "UPDATE bookings SET status = 'pending' WHERE status = 'booked'"
    )
    op.execute(
        "UPDATE bookings SET status = 'accepted' WHERE status IN "
        "('confirmed','en_route','arrived','in_progress','done')"
    )

    # Recreate enum without new values.
    op.execute("ALTER TABLE bookings ALTER COLUMN status TYPE TEXT")
    op.execute(f"DROP TYPE {ENUM_NAME}")
    op.execute(
        "CREATE TYPE {enum_name} AS ENUM ({values})".format(
            enum_name=ENUM_NAME,
            values=", ".join([f"'{v}'" for v in OLD_STATUSES]),
        )
    )
    op.execute(
        f"ALTER TABLE bookings ALTER COLUMN status TYPE {ENUM_NAME} "
        f"USING status::{ENUM_NAME}"
    )
