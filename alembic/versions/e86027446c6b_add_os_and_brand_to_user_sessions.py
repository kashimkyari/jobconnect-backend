"""add os and brand to user_sessions

Revision ID: e86027446c6b
Revises: e91cc37d4e4c
Create Date: 2026-03-21 21:22:38.229754

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e86027446c6b'
down_revision: Union[str, Sequence[str], None] = 'e91cc37d4e4c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('user_sessions', sa.Column('device_model', sa.String(), nullable=True))
    op.add_column('user_sessions', sa.Column('device_brand', sa.String(), nullable=True))
    op.add_column('user_sessions', sa.Column('os_name', sa.String(), nullable=True))
    op.add_column('user_sessions', sa.Column('os_version', sa.String(), nullable=True))

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('user_sessions', 'os_version')
    op.drop_column('user_sessions', 'os_name')
    op.drop_column('user_sessions', 'device_brand')
    op.drop_column('user_sessions', 'device_model')
