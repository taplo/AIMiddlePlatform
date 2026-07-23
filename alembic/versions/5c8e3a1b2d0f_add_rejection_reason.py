"""add rejection_reason to tasks

Revision ID: 5c8e3a1b2d0f
Revises: 0ccd4b670e4f
Create Date: 2026-07-11 22:20:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '5c8e3a1b2d0f'
down_revision: str | Sequence[str] | None = '0ccd4b670e4f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('rejection_reason', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'rejection_reason')
