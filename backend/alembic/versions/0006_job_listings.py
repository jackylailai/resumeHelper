"""job_listings: scraped JD table linkable to job_analyses

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_listings",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("company", sa.Text, nullable=False),
        sa.Column("location", sa.Text, nullable=True),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("raw_json", JSONB, nullable=True),
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "job_analysis_id",
            UUID(as_uuid=True),
            sa.ForeignKey("job_analyses.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
