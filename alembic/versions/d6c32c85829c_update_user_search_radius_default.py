"""update_user_search_radius_default

Revision ID: d6c32c85829c
Revises: 8eefef3c6367
Create Date: 2026-03-27 22:57:32.133818

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6c32c85829c'
down_revision: Union[str, Sequence[str], None] = '8eefef3c6367'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Update user search_radius_km default to 50km."""
    # Standardize search_radius_km default from 10 to 50
    op.alter_column('users', 'search_radius_km',
               existing_type=sa.Integer(),
               server_default=sa.text('50'),
               existing_server_default=sa.text('10'))


def downgrade() -> None:
    """Downgrade schema: Revert user search_radius_km default to 10km."""
    op.alter_column('users', 'search_radius_km',
               existing_type=sa.Integer(),
               server_default=sa.text('10'),
               existing_server_default=sa.text('50'))
