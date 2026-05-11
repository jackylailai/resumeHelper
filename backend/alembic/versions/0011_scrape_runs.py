"""scrape_runs: track scraper executions and ingestion stats

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_listings",
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "scrape_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("limit", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partial', 'failed')",
            name="ck_scrape_runs_status",
        ),
    )
    op.create_index("ix_scrape_runs_source", "scrape_runs", ["source"])
    op.create_index("ix_scrape_runs_started_at", "scrape_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_scrape_runs_started_at", table_name="scrape_runs")
    op.drop_index("ix_scrape_runs_source", table_name="scrape_runs")
    op.drop_table("scrape_runs")
    op.drop_column("job_listings", "changed_at")
