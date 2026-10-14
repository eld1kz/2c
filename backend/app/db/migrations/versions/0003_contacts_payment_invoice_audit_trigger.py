"""counterparty contact email, sandbox payment invoice, append-only audit trigger

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUDIT_GUARD_MESSAGE = 'audit_events is append-only'


def upgrade() -> None:
    with op.batch_alter_table('counterparties') as batch:
        batch.add_column(sa.Column('contact_email', sa.String(length=254), nullable=True))
    with op.batch_alter_table('sandbox_payments') as batch:
        batch.add_column(sa.Column('invoice_id', sa.Integer(), nullable=False))
        batch.create_foreign_key('fk_sandbox_payments_invoice_id', 'invoices', ['invoice_id'], ['id'])

    if op.get_bind().dialect.name == 'postgresql':
        op.execute(f"""
            CREATE FUNCTION audit_events_append_only() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION '{AUDIT_GUARD_MESSAGE}';
            END;
            $$ LANGUAGE plpgsql
        """)
        op.execute("""
            CREATE TRIGGER audit_events_append_only
            BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()
        """)
    else:
        for verb in ('UPDATE', 'DELETE'):
            op.execute(f"""
                CREATE TRIGGER audit_events_no_{verb.lower()}
                BEFORE {verb} ON audit_events
                BEGIN SELECT RAISE(ABORT, '{AUDIT_GUARD_MESSAGE}'); END
            """)


def downgrade() -> None:
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP TRIGGER audit_events_append_only ON audit_events')
        op.execute('DROP FUNCTION audit_events_append_only()')
    else:
        op.execute('DROP TRIGGER audit_events_no_update')
        op.execute('DROP TRIGGER audit_events_no_delete')
    with op.batch_alter_table('sandbox_payments') as batch:
        batch.drop_constraint('fk_sandbox_payments_invoice_id', type_='foreignkey')
        batch.drop_column('invoice_id')
    with op.batch_alter_table('counterparties') as batch:
        batch.drop_column('contact_email')
