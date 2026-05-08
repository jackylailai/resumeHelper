"""job listings for scraped JD browser

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("raw_json", postgresql.JSONB(), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("job_analysis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("source", "source_id", name="uq_job_listings_source"),
    )
    op.create_index("ix_job_listings_source", "job_listings", ["source"])
    op.create_index(
        "ix_job_listings_job_analysis_id", "job_listings", ["job_analysis_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_job_listings_job_analysis_id", table_name="job_listings")
    op.drop_index("ix_job_listings_source", table_name="job_listings")
    op.drop_table("job_listings")
