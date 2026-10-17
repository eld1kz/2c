"""cfo_memos: the cached weekly CFO memo (Phase 6)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cfo_memos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('as_of', sa.Date(), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('generated_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('citations', sa.JSON(), nullable=False),
        sa.Column('facts_digest', sa.String(64), nullable=False),
    )
    op.create_index('ix_cfo_memos_business_id', 'cfo_memos', ['business_id'])


def downgrade() -> None:
    op.drop_index('ix_cfo_memos_business_id', table_name='cfo_memos')
    op.drop_table('cfo_memos')
