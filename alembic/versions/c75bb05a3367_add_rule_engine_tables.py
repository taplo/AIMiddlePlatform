"""add_rule_engine_tables

Revision ID: c75bb05a3367
Revises: 5c8e3a1b2d0f
Create Date: 2026-07-12 13:22:43.174409

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c75bb05a3367'
down_revision: str | Sequence[str] | None = '5c8e3a1b2d0f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('rules',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('rule_type', sa.String(length=32), nullable=False),
    sa.Column('config', sa.Text(), nullable=False),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('description', sa.String(length=512), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('rule_bindings',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('rule_id', sa.Integer(), nullable=False),
    sa.Column('camera_id', sa.String(length=64), nullable=True),
    sa.Column('scene_type', sa.String(length=64), nullable=True),
    sa.Column('config_overrides', sa.Text(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['rule_id'], ['rules.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('alerts') as batch_op:
        batch_op.add_column(sa.Column('rule_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('binding_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('metadata', sa.Text(), nullable=True))
        batch_op.create_foreign_key('fk_alerts_rule_id', 'rules', ['rule_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('alerts') as batch_op:
        batch_op.drop_constraint('fk_alerts_rule_id', type_='foreignkey')
        batch_op.drop_column('metadata')
        batch_op.drop_column('binding_id')
        batch_op.drop_column('rule_id')
    op.drop_table('rule_bindings')
    op.drop_table('rules')
