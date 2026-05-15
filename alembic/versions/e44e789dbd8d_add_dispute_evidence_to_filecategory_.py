"""add dispute_evidence to filecategory enum

Revision ID: e44e789dbd8d
Revises: b41135480ad1
Create Date: 2026-03-21 11:33:44.555397

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e44e789dbd8d'
down_revision: Union[str, Sequence[str], None] = 'b41135480ad1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add dispute_evidence to filecategory enum
    op.execute("COMMIT")
    op.execute("ALTER TYPE filecategory ADD VALUE 'dispute_evidence'")


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL doesn't easily support removing enum values
    pass
