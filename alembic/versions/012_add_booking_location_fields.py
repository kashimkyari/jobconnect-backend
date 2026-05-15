"""Add booking location fields

Revision ID: 012
Revises: 011
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa


revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("bookings", sa.Column("address", sa.String(length=255), nullable=True))
    op.add_column("bookings", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("bookings", sa.Column("longitude", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("bookings", "longitude")
    op.drop_column("bookings", "latitude")
    op.drop_column("bookings", "address")
