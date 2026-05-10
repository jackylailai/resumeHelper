"""baseline_profile.structured_data JSONB column

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-10
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "baseline_profile",
        sa.Column("structured_data", JSONB(), nullable=True),
    )
    op.create_index(
        "ix_baseline_profile_structured_data",
        "baseline_profile",
        ["structured_data"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_baseline_profile_structured_data",
        table_name="baseline_profile",
    )
    op.drop_column("baseline_profile", "structured_data")
