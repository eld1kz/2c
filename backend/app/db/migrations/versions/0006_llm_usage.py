"""llm_usage: tokens and cost per model call, for the daily AI budget

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_usage',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('cache_read_tokens', sa.Integer(), nullable=False),
        sa.Column('cache_write_tokens', sa.Integer(), nullable=False),
        sa.Column('cost_microusd', sa.BigInteger(), nullable=False),
    )
    op.create_index('ix_llm_usage_day', 'llm_usage', ['day'])


def downgrade() -> None:
    op.drop_index('ix_llm_usage_day', table_name='llm_usage')
    op.drop_table('llm_usage')
