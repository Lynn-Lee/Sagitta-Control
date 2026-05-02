"""Sprint C1：system_config 和 operation_log 表

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-23
"""
import sqlalchemy as sa

from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'system_config',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('config_key', sa.String(100), nullable=False, unique=True),
        sa.Column('config_value', sa.Text(), nullable=False, default=''),
        sa.Column('is_encrypted', sa.Boolean(), nullable=False, default=False),
        sa.Column('description', sa.String(200), nullable=False, default=''),
        sa.Column('group', sa.String(50), nullable=False, default='basic'),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_syscfg_group', 'system_config', ['group'])
    op.create_index('ix_syscfg_tenant', 'system_config', ['tenant_id'])

    op.create_table(
        'operation_log',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False, default=0),
        sa.Column('username', sa.String(30), nullable=False, default=''),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('module', sa.String(50), nullable=False, default=''),
        sa.Column('detail', sa.Text(), nullable=False, default=''),
        sa.Column('ip_address', sa.String(50), nullable=False, default=''),
        sa.Column('result', sa.String(10), nullable=False, default='success'),
        sa.Column('remark', sa.String(500), nullable=False, default=''),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_oplog_user', 'operation_log', ['user_id'])
    op.create_index('ix_oplog_action', 'operation_log', ['action'])
    op.create_index('ix_oplog_module', 'operation_log', ['module'])
    op.create_index('ix_oplog_tenant', 'operation_log', ['tenant_id'])


def downgrade() -> None:
    op.drop_table('operation_log')
    op.drop_table('system_config')
