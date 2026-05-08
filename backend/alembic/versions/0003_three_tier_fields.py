"""three_tier_fields: add status, can_submit, skip_reason to job_analyses; pdf_url to generated_resumes

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add three-tier classification columns to job_analyses
    op.add_column(
        "job_analyses",
        sa.Column("status", sa.String(20), nullable=True),
    )
    op.add_column(
        "job_analyses",
        sa.Column("can_submit", sa.Boolean, nullable=False, server_default="false"),
    )
    op.add_column(
        "job_analyses",
        sa.Column("skip_reason", sa.Text, nullable=True),
    )

    # Add pdf_url to generated_resumes
    op.add_column(
        "generated_resumes",
        sa.Column("pdf_url", sa.Text, nullable=True),
    )

    # Add check constraint for status values (nullable so existing rows are OK)
    op.create_check_constraint(
        "ck_job_status",
        "job_analyses",
        "status IS NULL OR status IN ('ready_to_submit', 'needs_tailoring', 'skip')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_job_status", "job_analyses", type_="check")
    op.drop_column("generated_resumes", "pdf_url")
    op.drop_column("job_analyses", "skip_reason")
    op.drop_column("job_analyses", "can_submit")
    op.drop_column("job_analyses", "status")
