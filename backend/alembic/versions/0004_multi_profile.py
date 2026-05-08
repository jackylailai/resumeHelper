"""multi_profile: add name/created_at to baseline_profile; profile_id FK on job_analyses

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # baseline_profile: add name and created_at
    op.add_column("baseline_profile", sa.Column("name", sa.String(255), nullable=True))
    op.add_column(
        "baseline_profile",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE baseline_profile SET created_at = updated_at")

    # job_analyses: add profile_id FK
    op.add_column("job_analyses", sa.Column("profile_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_job_analyses_profile_id",
        "job_analyses", "baseline_profile",
        ["profile_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_job_analyses_profile_id", "job_analyses", ["profile_id"])

    # Change unique from jd_hash alone to (jd_hash, profile_id)
    op.drop_constraint("job_analyses_jd_hash_key", "job_analyses", type_="unique")
    op.create_unique_constraint(
        "uq_job_analyses_jd_hash_profile",
        "job_analyses",
        ["jd_hash", "profile_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_job_analyses_jd_hash_profile", "job_analyses", type_="unique")
    op.create_unique_constraint("job_analyses_jd_hash_key", "job_analyses", ["jd_hash"])
    op.drop_index("ix_job_analyses_profile_id", table_name="job_analyses")
    op.drop_constraint("fk_job_analyses_profile_id", "job_analyses", type_="foreignkey")
    op.drop_column("job_analyses", "profile_id")
    op.drop_column("baseline_profile", "created_at")
    op.drop_column("baseline_profile", "name")
