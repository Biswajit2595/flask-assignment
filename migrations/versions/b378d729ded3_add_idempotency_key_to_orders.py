"""add idempotency key to orders

Revision ID: b378d729ded3
Revises: 8d61dba822fd
Create Date: 2026-03-30 23:10:13.385751

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b378d729ded3'
down_revision = '8d61dba822fd'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'idempotency_key',
                sa.String(length=255),
                nullable=True,
                unique=True      
            )
        )

def downgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('idempotency_key')