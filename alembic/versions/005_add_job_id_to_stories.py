"""Add job_id support to stories for employer job stories

Revision ID: 005
Revises: None
Create Date: 2026-03-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '005'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    story_columns = {col["name"] for col in inspector.get_columns("stories")}
    if "job_id" not in story_columns:
        op.add_column("stories", sa.Column("job_id", sa.Integer(), nullable=True))

    story_indexes = {idx["name"] for idx in inspector.get_indexes("stories")}
    if "ix_stories_job_id" not in story_indexes:
        op.create_index("ix_stories_job_id", "stories", ["job_id"])

    story_fks = {fk["name"] for fk in inspector.get_foreign_keys("stories")}
    if "fk_stories_job_id" not in story_fks:
        op.create_foreign_key(
            "fk_stories_job_id",
            "stories",
            "jobs",
            ["job_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    story_fks = {fk["name"] for fk in inspector.get_foreign_keys("stories")}
    if "fk_stories_job_id" in story_fks:
        op.drop_constraint("fk_stories_job_id", "stories", type_="foreignkey")

    story_indexes = {idx["name"] for idx in inspector.get_indexes("stories")}
    if "ix_stories_job_id" in story_indexes:
        op.drop_index("ix_stories_job_id", table_name="stories")

    story_columns = {col["name"] for col in inspector.get_columns("stories")}
    if "job_id" in story_columns:
        op.drop_column("stories", "job_id")
