"""resume_beautification table

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-10
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resume_beautifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "generated_resume_id",
            UUID(as_uuid=True),
            sa.ForeignKey("generated_resumes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "style",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'modern'"),
        ),
        sa.Column("html_content", sa.Text(), nullable=False),
        sa.Column("pdf_path", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_resume_beautifications_generated_resume_id",
        "resume_beautifications",
        ["generated_resume_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_resume_beautifications_generated_resume_id",
        table_name="resume_beautifications",
    )
    op.drop_table("resume_beautifications")
