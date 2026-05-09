"""applications: track application pipeline

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "job_listing_id",
            UUID(as_uuid=True),
            sa.ForeignKey("job_listings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "job_analysis_id",
            UUID(as_uuid=True),
            sa.ForeignKey("job_analyses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "generated_resume_id",
            UUID(as_uuid=True),
            sa.ForeignKey("generated_resumes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="planned"),
        sa.Column("follow_up_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'applied', 'interviewing', 'rejected', 'offer', 'archived')",
            name="ck_applications_status",
        ),
    )
    op.create_index("ix_applications_job_listing_id", "applications", ["job_listing_id"])
    op.create_index("ix_applications_job_analysis_id", "applications", ["job_analysis_id"])
    op.create_index(
        "ix_applications_generated_resume_id",
        "applications",
        ["generated_resume_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_applications_generated_resume_id", table_name="applications")
    op.drop_index("ix_applications_job_analysis_id", table_name="applications")
    op.drop_index("ix_applications_job_listing_id", table_name="applications")
    op.drop_table("applications")
