"""add is_deleted to user_sessions

Revision ID: e91cc37d4e4c
Revises: d03e40b2fc47
Create Date: 2026-03-21 21:17:25.393673

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e91cc37d4e4c'
down_revision: Union[str, Sequence[str], None] = 'd03e40b2fc47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('user_sessions', sa.Column('is_deleted', sa.Boolean(), server_default='False', nullable=False))
    op.create_index(op.f('ix_user_sessions_is_deleted'), 'user_sessions', ['is_deleted'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_user_sessions_is_deleted'), table_name='user_sessions')
    op.drop_column('user_sessions', 'is_deleted')
