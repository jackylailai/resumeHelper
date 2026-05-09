"""profile_default: mark the default baseline profile

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "baseline_profile",
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("baseline_profile", "is_default", server_default=None)


def downgrade() -> None:
    op.drop_column("baseline_profile", "is_default")
