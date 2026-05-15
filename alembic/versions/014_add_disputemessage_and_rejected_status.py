"""add_disputemessage_and_rejected_status

Revision ID: 014
Revises: 013
Create Date: 2026-03-21 10:39:30.498649

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '014'
down_revision: Union[str, Sequence[str], None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add REJECTED to DisputeStatus enum
    op.execute("ALTER TYPE disputestatus ADD VALUE IF NOT EXISTS 'REJECTED'")

    # Create dispute_messages table
    op.create_table('dispute_messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('dispute_id', sa.Integer(), nullable=False),
    sa.Column('sender_id', sa.Integer(), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('is_admin_reply', sa.Boolean(), nullable=True),
    sa.Column('evidence_url', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['dispute_id'], ['disputes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_dispute_messages_created_at'), 'dispute_messages', ['created_at'], unique=False)
    op.create_index(op.f('ix_dispute_messages_dispute_id'), 'dispute_messages', ['dispute_id'], unique=False)
    op.create_index(op.f('ix_dispute_messages_id'), 'dispute_messages', ['id'], unique=False)
    op.create_index(op.f('ix_dispute_messages_sender_id'), 'dispute_messages', ['sender_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_dispute_messages_sender_id'), table_name='dispute_messages')
    op.drop_index(op.f('ix_dispute_messages_id'), table_name='dispute_messages')
    op.drop_index(op.f('ix_dispute_messages_dispute_id'), table_name='dispute_messages')
    op.drop_index(op.f('ix_dispute_messages_created_at'), table_name='dispute_messages')
    op.drop_table('dispute_messages')

    # Note: PostgreSQL does not support dropping a value from an ENUM type.
    # We would drop and recreate the type but it's used in disputes table, so we leave it.
