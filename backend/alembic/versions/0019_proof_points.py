"""proof points library

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-19
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proof_points",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("baseline_profile.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("metrics", sa.Text(), nullable=True),
        sa.Column(
            "skills",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "tags",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("situation", sa.Text(), nullable=True),
        sa.Column("task", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_proof_points_profile_id", "proof_points", ["profile_id"])
    op.create_index("ix_proof_points_created_at", "proof_points", ["created_at"])
    op.create_index("ix_proof_points_updated_at", "proof_points", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_proof_points_updated_at", table_name="proof_points")
    op.drop_index("ix_proof_points_created_at", table_name="proof_points")
    op.drop_index("ix_proof_points_profile_id", table_name="proof_points")
    op.drop_table("proof_points")
