"""instance_database 表

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-24
"""
import sqlalchemy as sa

from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'instance_database',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('instance_id', sa.Integer(),
                  sa.ForeignKey('sql_instance.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('db_name', sa.String(64), nullable=False),
        sa.Column('remark', sa.String(200), nullable=False, default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index('ix_instdb_instance', 'instance_database', ['instance_id'])
    op.create_unique_constraint(
        'uq_instance_db_name', 'instance_database', ['instance_id', 'db_name']
    )


def downgrade() -> None:
    op.drop_table('instance_database')
