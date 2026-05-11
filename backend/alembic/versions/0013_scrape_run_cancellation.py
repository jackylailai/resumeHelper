"""scrape_runs: support cancellation states

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-11
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_scrape_runs_status", "scrape_runs", type_="check")
    op.create_check_constraint(
        "ck_scrape_runs_status",
        "scrape_runs",
        (
            "status IN ("
            "'queued', 'running', 'cancel_requested', 'cancelled', "
            "'succeeded', 'partial', 'failed'"
            ")"
        ),
    )


def downgrade() -> None:
    op.drop_constraint("ck_scrape_runs_status", "scrape_runs", type_="check")
    op.execute(
        "UPDATE scrape_runs SET status = 'failed' "
        "WHERE status IN ('cancel_requested', 'cancelled')"
    )
    op.create_check_constraint(
        "ck_scrape_runs_status",
        "scrape_runs",
        "status IN ('queued', 'running', 'succeeded', 'partial', 'failed')",
    )
