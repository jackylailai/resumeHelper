"""persist evaluation job description

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("evaluation_jobs", sa.Column("job_description", sa.Text(), nullable=True))
    op.execute("UPDATE evaluation_jobs SET job_description = '' WHERE job_description IS NULL")
    op.alter_column("evaluation_jobs", "job_description", nullable=False)


def downgrade() -> None:
    op.drop_column("evaluation_jobs", "job_description")
