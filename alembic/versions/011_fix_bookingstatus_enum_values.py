"""Fix bookingstatus enum values to lowercase

Revision ID: 011
Revises: 010
Create Date: 2026-03-13
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


OLD_ENUM = "bookingstatus"
NEW_ENUM = "bookingstatus_new"

LOWERCASE_VALUES = [
    "pending",
    "accepted",
    "rejected",
    "cancelled",
    "completed",
    "booked",
    "confirmed",
    "en_route",
    "arrived",
    "in_progress",
    "done",
]


def upgrade():
    # Create new enum with lowercase values.
    op.execute(
        "CREATE TYPE {new} AS ENUM ({values})".format(
            new=NEW_ENUM,
            values=", ".join([f"'{v}'" for v in LOWERCASE_VALUES]),
        )
    )

    # Drop default to avoid cast issues, then convert to lowercase text and cast.
    op.execute("ALTER TABLE bookings ALTER COLUMN status DROP DEFAULT")
    op.execute(
        f"ALTER TABLE bookings ALTER COLUMN status TYPE {NEW_ENUM} "
        f"USING lower(status::text)::{NEW_ENUM}"
    )

    # Replace old enum with the new one.
    op.execute(f"DROP TYPE {OLD_ENUM}")
    op.execute(f"ALTER TYPE {NEW_ENUM} RENAME TO {OLD_ENUM}")

    # Restore default.
    op.execute("ALTER TABLE bookings ALTER COLUMN status SET DEFAULT 'booked'")


def downgrade():
    # Downgrade not supported cleanly because original enum values are unknown-case.
    # Recreate an uppercase enum to match legacy schema if needed.
    uppercase_values = [v.upper() for v in LOWERCASE_VALUES]
    old_upper_enum = "bookingstatus_old"

    op.execute(
        "CREATE TYPE {old} AS ENUM ({values})".format(
            old=old_upper_enum,
            values=", ".join([f"'{v}'" for v in uppercase_values]),
        )
    )
    op.execute("ALTER TABLE bookings ALTER COLUMN status DROP DEFAULT")
    op.execute(
        f"ALTER TABLE bookings ALTER COLUMN status TYPE {old_upper_enum} "
        f"USING upper(status::text)::{old_upper_enum}"
    )
    op.execute(f"DROP TYPE {OLD_ENUM}")
    op.execute(f"ALTER TYPE {old_upper_enum} RENAME TO {OLD_ENUM}")
    op.execute("ALTER TABLE bookings ALTER COLUMN status SET DEFAULT 'BOOKED'")
