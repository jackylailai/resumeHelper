"""generated_resumes: track user revisions and PDF export state

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generated_resumes",
        sa.Column(
            "revision_source",
            sa.String(20),
            nullable=False,
            server_default="ai_draft",
        ),
    )
    op.add_column(
        "generated_resumes",
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generated_resumes", "exported_at")
    op.drop_column("generated_resumes", "revision_source")
