"""category rules

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('category_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Enum('keyword', 'name', name='rulekind', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('pattern', sa.String(length=200), nullable=False),
    sa.Column('direction', sa.Enum('in', 'out', 'any', name='ruledirection', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('category', sa.Enum('revenue_retail', 'revenue_wholesale', 'cogs_beans', 'cogs_packaging', 'rent', 'utilities', 'payroll', 'software', 'equipment', 'logistics', 'marketing', 'fees', 'taxes', 'transfer', 'other', name='category', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('source', sa.Enum('seed', 'human', name='rulesource', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('category_rules')
