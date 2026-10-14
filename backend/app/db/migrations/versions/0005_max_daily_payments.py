"""policy: cumulative daily payment cap

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('policies') as batch:
        # Existing policies get the default: 2 × the $5,000 single-payment limit, in cents.
        batch.add_column(sa.Column('max_daily_payments', sa.BigInteger(), nullable=False, server_default='1000000'))


def downgrade() -> None:
    with op.batch_alter_table('policies') as batch:
        batch.drop_column('max_daily_payments')
