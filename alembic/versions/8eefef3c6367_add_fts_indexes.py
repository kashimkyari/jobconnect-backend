"""add_fts_indexes

Revision ID: 8eefef3c6367
Revises: e86027446c6b
Create Date: 2026-03-23 23:22:05.372123

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8eefef3c6367'
down_revision: Union[str, Sequence[str], None] = 'e86027446c6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Users FTS Index
    op.execute("""
        CREATE INDEX idx_users_fts ON users USING GIN (
            to_tsvector('english', 
                coalesce(first_name, '') || ' ' || 
                coalesce(last_name, '') || ' ' || 
                coalesce(headline, '') || ' ' || 
                coalesce(about_me, '') || ' ' || 
                coalesce(city, '') || ' ' || 
                coalesce(service_category, '') || ' ' ||
                coalesce(skills::text, '')
            )
        )
    """)
    
    # Services FTS Index
    op.execute("""
        CREATE INDEX idx_services_fts ON services USING GIN (
            to_tsvector('english', 
                coalesce(name, '') || ' ' || 
                coalesce(description, '') || ' ' || 
                coalesce(city, '')
            )
        )
    """)
    
    # Jobs FTS Index
    op.execute("""
        CREATE INDEX idx_jobs_fts ON jobs USING GIN (
            to_tsvector('english', 
                coalesce(title, '') || ' ' || 
                coalesce(description, '') || ' ' || 
                coalesce(city, '')
            )
        )
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_users_fts")
    op.execute("DROP INDEX IF EXISTS idx_services_fts")
    op.execute("DROP INDEX IF EXISTS idx_jobs_fts")
