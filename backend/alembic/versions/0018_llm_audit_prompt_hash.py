"""add prompt hash to LLM audit logs

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-19
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_audit_logs",
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_audit_logs", "prompt_hash")
