"""pdf_path: persist uploaded PDF on disk, store path on baseline_profile

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("baseline_profile", sa.Column("pdf_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("baseline_profile", "pdf_path")
