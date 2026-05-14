"""prompt lifecycle metadata

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_analyses",
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "job_analyses",
        sa.Column("llm_backend", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "job_analyses",
        sa.Column("llm_model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "generated_resumes",
        sa.Column("llm_backend", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "generated_resumes",
        sa.Column("llm_model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "resume_beautifications",
        sa.Column("llm_backend", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "resume_beautifications",
        sa.Column("llm_model", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resume_beautifications", "llm_model")
    op.drop_column("resume_beautifications", "llm_backend")
    op.drop_column("generated_resumes", "llm_model")
    op.drop_column("generated_resumes", "llm_backend")
    op.drop_column("job_analyses", "llm_model")
    op.drop_column("job_analyses", "llm_backend")
    op.drop_column("job_analyses", "prompt_version")
