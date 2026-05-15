"""Add job repost lineage and service idempotency columns

Revision ID: 009
Revises: 008
Create Date: 2026-03-08
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("jobs", "last_request_id", existing_type=sa.String(length=36), type_=sa.String(length=128))
    op.add_column("jobs", sa.Column("repeated_from_job_id", sa.Integer(), nullable=True))
    op.create_index("ix_jobs_repeated_from_job_id", "jobs", ["repeated_from_job_id"])
    op.create_foreign_key(
        "fk_jobs_repeated_from_job_id_jobs",
        "jobs",
        "jobs",
        ["repeated_from_job_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("services", sa.Column("last_request_id", sa.String(length=128), nullable=True))
    op.add_column("services", sa.Column("last_request_at", sa.DateTime(), nullable=True))
    op.create_index("ix_services_last_request_id", "services", ["last_request_id"])


def downgrade():
    op.drop_index("ix_services_last_request_id", table_name="services")
    op.drop_column("services", "last_request_at")
    op.drop_column("services", "last_request_id")

    op.drop_constraint("fk_jobs_repeated_from_job_id_jobs", "jobs", type_="foreignkey")
    op.drop_index("ix_jobs_repeated_from_job_id", table_name="jobs")
    op.drop_column("jobs", "repeated_from_job_id")
    op.alter_column("jobs", "last_request_id", existing_type=sa.String(length=128), type_=sa.String(length=36))
