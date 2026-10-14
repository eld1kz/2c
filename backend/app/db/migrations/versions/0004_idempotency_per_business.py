"""idempotency keys unique per business, not globally

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-14

"""
from typing import Sequence, Union

from alembic import op


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 0001 created the global unique constraint unnamed; name it the way each dialect did.
SQLITE_NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _old_name() -> str:
    return 'actions_idempotency_key_key' if op.get_bind().dialect.name == 'postgresql' else 'uq_actions_idempotency_key'


def upgrade() -> None:
    with op.batch_alter_table('actions', naming_convention=SQLITE_NAMING) as batch:
        batch.drop_constraint(_old_name(), type_='unique')
        batch.create_unique_constraint('uq_actions_business_idempotency_key', ['business_id', 'idempotency_key'])


def downgrade() -> None:
    with op.batch_alter_table('actions', naming_convention=SQLITE_NAMING) as batch:
        batch.drop_constraint('uq_actions_business_idempotency_key', type_='unique')
        batch.create_unique_constraint(_old_name(), ['idempotency_key'])
