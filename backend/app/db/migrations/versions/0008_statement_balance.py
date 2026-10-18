"""transactions.statement_balance: the running balance printed on the bank CSV row (Phase 6b)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transactions', sa.Column('statement_balance', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('transactions', 'statement_balance')
