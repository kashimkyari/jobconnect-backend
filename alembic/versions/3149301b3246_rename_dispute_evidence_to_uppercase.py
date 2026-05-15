"""rename dispute_evidence to uppercase

Revision ID: 3149301b3246
Revises: e44e789dbd8d
Create Date: 2026-03-21 11:38:46.581283

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3149301b3246'
down_revision: Union[str, Sequence[str], None] = 'e44e789dbd8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("COMMIT")
    op.execute("ALTER TYPE filecategory RENAME VALUE 'dispute_evidence' TO 'DISPUTE_EVIDENCE'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("COMMIT")
    op.execute("ALTER TYPE filecategory RENAME VALUE 'DISPUTE_EVIDENCE' TO 'dispute_evidence'")
