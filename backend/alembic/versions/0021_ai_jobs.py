"""ai jobs

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_jobs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("parent_job_id", UUID(as_uuid=True), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "run_after",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "progress_current",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("job_analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("job_listing_id", UUID(as_uuid=True), nullable=True),
        sa.Column("generated_resume_id", UUID(as_uuid=True), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column(
            "input_payload",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("result_payload", JSONB, nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
            (
                "kind IN ("
                "'tailor', 'evaluate', 'evaluate_bulk', "
                "'evaluate_listing', 'evaluate_pending_listings'"
                ")"
            ),
            name="ck_ai_jobs_kind",
        ),
        sa.CheckConstraint(
            (
                "status IN ("
                "'queued', 'running', 'retry_wait', 'cancel_requested', "
                "'cancelled', 'succeeded', 'failed'"
                ")"
            ),
            name="ck_ai_jobs_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_ai_jobs_attempts_nonnegative"),
        sa.CheckConstraint("max_attempts >= 1", name="ck_ai_jobs_max_attempts_positive"),
        sa.CheckConstraint(
            "progress_current >= 0",
            name="ck_ai_jobs_progress_current_nonnegative",
        ),
        sa.CheckConstraint(
            "progress_total IS NULL OR progress_total >= 0",
            name="ck_ai_jobs_progress_total_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["parent_job_id"],
            ["ai_jobs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["baseline_profile.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_analysis_id"],
            ["job_analyses.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_listing_id"],
            ["job_listings.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["generated_resume_id"],
            ["generated_resumes.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("dedupe_key", name="uq_ai_jobs_dedupe_key"),
    )
    op.create_index("ix_ai_jobs_kind", "ai_jobs", ["kind"])
    op.create_index("ix_ai_jobs_status", "ai_jobs", ["status"])
    op.create_index("ix_ai_jobs_parent_job_id", "ai_jobs", ["parent_job_id"])
    op.create_index("ix_ai_jobs_profile_id", "ai_jobs", ["profile_id"])
    op.create_index("ix_ai_jobs_job_analysis_id", "ai_jobs", ["job_analysis_id"])
    op.create_index("ix_ai_jobs_job_listing_id", "ai_jobs", ["job_listing_id"])
    op.create_index("ix_ai_jobs_generated_resume_id", "ai_jobs", ["generated_resume_id"])
    op.create_index("ix_ai_jobs_request_id", "ai_jobs", ["request_id"])
    op.create_index("ix_ai_jobs_created_at", "ai_jobs", ["created_at"])
    op.create_index("ix_ai_jobs_updated_at", "ai_jobs", ["updated_at"])
    op.create_index(
        "ix_ai_jobs_worker_queue",
        "ai_jobs",
        ["status", "run_after", "priority", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_jobs_worker_queue", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_updated_at", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_created_at", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_request_id", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_generated_resume_id", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_job_listing_id", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_job_analysis_id", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_profile_id", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_parent_job_id", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_status", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_kind", table_name="ai_jobs")
    op.drop_table("ai_jobs")
