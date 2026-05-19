"""scrape_runs: advanced JD-body filter columns

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-15
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scrape_runs",
        sa.Column("skipped_by_filter", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "scrape_runs",
        sa.Column("must_contain", JSONB(), nullable=True),
    )
    op.add_column(
        "scrape_runs",
        sa.Column(
            "match_mode",
            sa.String(length=8),
            nullable=False,
            server_default="all",
        ),
    )
    op.add_column(
        "scrape_runs",
        sa.Column(
            "regex",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_check_constraint(
        "ck_scrape_runs_match_mode",
        "scrape_runs",
        "match_mode IN ('all', 'any')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_scrape_runs_match_mode", "scrape_runs", type_="check")
    op.drop_column("scrape_runs", "regex")
    op.drop_column("scrape_runs", "match_mode")
    op.drop_column("scrape_runs", "must_contain")
    op.drop_column("scrape_runs", "skipped_by_filter")
