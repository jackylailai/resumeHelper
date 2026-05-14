"""llm audit logs

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_audit_logs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("workflow_step", sa.String(length=32), nullable=False),
        sa.Column("backend", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("output_hash", sa.String(length=64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_count_input", sa.Integer(), nullable=True),
        sa.Column("token_count_output", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("baseline_profile_id", sa.Integer(), nullable=True),
        sa.Column("job_analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("generated_resume_id", UUID(as_uuid=True), nullable=True),
        sa.Column("resume_beautification_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="ck_llm_audit_status",
        ),
        sa.ForeignKeyConstraint(
            ["baseline_profile_id"],
            ["baseline_profile.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["generated_resume_id"],
            ["generated_resumes.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_analysis_id"],
            ["job_analyses.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resume_beautification_id"],
            ["resume_beautifications.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_llm_audit_logs_baseline_profile_id",
        "llm_audit_logs",
        ["baseline_profile_id"],
    )
    op.create_index(
        "ix_llm_audit_logs_created_at",
        "llm_audit_logs",
        ["created_at"],
    )
    op.create_index(
        "ix_llm_audit_logs_generated_resume_id",
        "llm_audit_logs",
        ["generated_resume_id"],
    )
    op.create_index(
        "ix_llm_audit_logs_input_hash",
        "llm_audit_logs",
        ["input_hash"],
    )
    op.create_index(
        "ix_llm_audit_logs_job_analysis_id",
        "llm_audit_logs",
        ["job_analysis_id"],
    )
    op.create_index(
        "ix_llm_audit_logs_request_id",
        "llm_audit_logs",
        ["request_id"],
    )
    op.create_index(
        "ix_llm_audit_logs_resume_beautification_id",
        "llm_audit_logs",
        ["resume_beautification_id"],
    )
    op.create_index(
        "ix_llm_audit_logs_workflow_step",
        "llm_audit_logs",
        ["workflow_step"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_audit_logs_workflow_step", table_name="llm_audit_logs")
    op.drop_index(
        "ix_llm_audit_logs_resume_beautification_id",
        table_name="llm_audit_logs",
    )
    op.drop_index("ix_llm_audit_logs_request_id", table_name="llm_audit_logs")
    op.drop_index("ix_llm_audit_logs_job_analysis_id", table_name="llm_audit_logs")
    op.drop_index("ix_llm_audit_logs_input_hash", table_name="llm_audit_logs")
    op.drop_index(
        "ix_llm_audit_logs_generated_resume_id",
        table_name="llm_audit_logs",
    )
    op.drop_index("ix_llm_audit_logs_created_at", table_name="llm_audit_logs")
    op.drop_index(
        "ix_llm_audit_logs_baseline_profile_id",
        table_name="llm_audit_logs",
    )
    op.drop_table("llm_audit_logs")
