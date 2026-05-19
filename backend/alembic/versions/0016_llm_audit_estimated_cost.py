"""add estimated LLM cost to audit logs

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-18 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_audit_logs",
        sa.Column("estimated_cost_micros", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_audit_logs", "estimated_cost_micros")
