"""poc_schema: replace 4-table design with 3-table POC schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-05
"""
from alembic import op
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql  # noqa: F401
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old tables using raw SQL CASCADE to handle FK dependencies cleanly
    op.execute("DROP TABLE IF EXISTS evaluation_cache CASCADE")
    op.execute("DROP TABLE IF EXISTS evaluation_jobs CASCADE")
    op.execute("DROP TABLE IF EXISTS resume_evaluations CASCADE")
    op.execute("DROP TABLE IF EXISTS resume_versions CASCADE")
    op.execute("DROP TABLE IF EXISTS resumes CASCADE")

    # baseline_profile — single row, upserted
    op.create_table(
        "baseline_profile",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("skills_text", sa.Text, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # job_analyses — one row per unique JD
    op.create_table(
        "job_analyses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("jd_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("jd_snippet", sa.Text, nullable=True),
        sa.Column("jd_full_text", sa.Text, nullable=False),
        sa.Column("score", sa.Integer, nullable=True),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("strengths", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("gaps", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("threshold_met", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_job_score_range"),
    )
    op.create_index("ix_job_analyses_jd_hash", "job_analyses", ["jd_hash"])
    op.create_index("ix_job_analyses_created_at", "job_analyses", ["created_at"])

    # generated_resumes — many per job_analysis
    op.create_table(
        "generated_resumes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "job_analysis_id",
            UUID(as_uuid=True),
            sa.ForeignKey("job_analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resume_text", sa.Text, nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_generated_resumes_job_analysis_id",
        "generated_resumes",
        ["job_analysis_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("generated_resumes")
    op.drop_table("job_analyses")
    op.drop_table("baseline_profile")
