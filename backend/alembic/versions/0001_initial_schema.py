"""Sprint 1 初始数据库结构

Revision ID: 0001
Revises:
Create Date: 2026-03-22

"""
import sqlalchemy as sa

from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── permission ──────────────────────────────────────────
    op.create_table(
        'permission',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('codename', sa.String(100), nullable=False, unique=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── resource_group ────────────────────────────────────────
    op.create_table(
        'resource_group',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('group_name', sa.String(100), nullable=False, unique=True),
        sa.Column('group_name_cn', sa.String(100), nullable=False, default=''),
        sa.Column('ding_webhook', sa.String(500), nullable=False, default=''),
        sa.Column('feishu_webhook', sa.String(500), nullable=False, default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── sql_users ─────────────────────────────────────────────
    op.create_table(
        'sql_users',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('username', sa.String(30), nullable=False, unique=True),
        sa.Column('display_name', sa.String(50), nullable=False, default=''),
        sa.Column('password', sa.String(128), nullable=False),
        sa.Column('email', sa.String(100), nullable=False, default=''),
        sa.Column('phone', sa.String(20), nullable=False, default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, default=False),
        sa.Column('auth_type', sa.String(20), nullable=False, default='local'),
        sa.Column('external_id', sa.String(200), nullable=False, default=''),
        sa.Column('totp_secret', sa.String(100), nullable=True),
        sa.Column('totp_enabled', sa.Boolean(), nullable=False, default=False),
        sa.Column('remark', sa.String(500), nullable=False, default=''),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_users_tenant', 'sql_users', ['tenant_id'])
    op.create_index('ix_users_auth_type', 'sql_users', ['auth_type'])

    # ── user_resource_group (M2M) ─────────────────────────────
    op.create_table(
        'user_resource_group',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('sql_users.id', ondelete='CASCADE')),
        sa.Column('resource_group_id', sa.Integer(), sa.ForeignKey('resource_group.id', ondelete='CASCADE')),
    )

    # ── user_permission (M2M) ─────────────────────────────────
    op.create_table(
        'user_permission',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('sql_users.id', ondelete='CASCADE')),
        sa.Column('permission_id', sa.Integer(), sa.ForeignKey('permission.id', ondelete='CASCADE')),
    )

    # ── ssh_tunnel ────────────────────────────────────────────
    op.create_table(
        'ssh_tunnel',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tunnel_name', sa.String(50), nullable=False, unique=True),
        sa.Column('host', sa.String(200), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False, default=22),
        sa.Column('user', sa.String(100), nullable=False),
        sa.Column('password', sa.String(500), nullable=True),
        sa.Column('private_key', sa.Text(), nullable=True),
        sa.Column('private_key_password', sa.String(500), nullable=True),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── sql_instance ──────────────────────────────────────────
    op.create_table(
        'sql_instance',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('instance_name', sa.String(50), nullable=False, unique=True),
        sa.Column('type', sa.Enum('master', 'slave', name='instance_type_enum'), nullable=False, default='master'),
        sa.Column('db_type', sa.String(20), nullable=False),
        sa.Column('mode', sa.String(10), nullable=False, default='standalone'),
        sa.Column('host', sa.String(200), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False),
        sa.Column('user', sa.String(200), nullable=False),
        sa.Column('password', sa.String(500), nullable=False),
        sa.Column('is_ssl', sa.Boolean(), nullable=False, default=False),
        sa.Column('ssl_ca', sa.Text(), nullable=True),
        sa.Column('db_name', sa.String(64), nullable=False, default=''),
        sa.Column('show_db_name_regex', sa.String(1024), nullable=False, default=''),
        sa.Column('remark', sa.String(500), nullable=False, default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('tunnel_id', sa.Integer(), sa.ForeignKey('ssh_tunnel.id', ondelete='SET NULL'), nullable=True),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_instance_db_type', 'sql_instance', ['db_type'])
    op.create_index('ix_instance_tenant', 'sql_instance', ['tenant_id'])

    # ── instance_tag ──────────────────────────────────────────
    op.create_table(
        'instance_tag',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tag_key', sa.String(50), nullable=False),
        sa.Column('tag_value', sa.String(200), nullable=False),
        sa.Column('instance_id', sa.Integer(), sa.ForeignKey('sql_instance.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('instance_id', 'tag_key', name='uq_instance_tag_key'),
    )
    op.create_index('ix_tag_instance', 'instance_tag', ['instance_id'])

    # ── instance_resource_group (M2M) ─────────────────────────
    op.create_table(
        'instance_resource_group',
        sa.Column('instance_id', sa.Integer(), sa.ForeignKey('sql_instance.id', ondelete='CASCADE')),
        sa.Column('resource_group_id', sa.Integer(), sa.ForeignKey('resource_group.id', ondelete='CASCADE')),
    )

    # ── sql_workflow ──────────────────────────────────────────
    op.create_table(
        'sql_workflow',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('workflow_name', sa.String(50), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('group_name', sa.String(100), nullable=False),
        sa.Column('instance_id', sa.Integer(), sa.ForeignKey('sql_instance.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('db_name', sa.String(64), nullable=False),
        sa.Column('syntax_type', sa.Integer(), nullable=False, default=0),
        sa.Column('is_backup', sa.Boolean(), nullable=False, default=True),
        sa.Column('engineer', sa.String(30), nullable=False),
        sa.Column('engineer_display', sa.String(50), nullable=False, default=''),
        sa.Column('engineer_id', sa.Integer(), sa.ForeignKey('sql_users.id'), nullable=False),
        sa.Column('status', sa.Integer(), nullable=False, default=0),
        sa.Column('audit_auth_groups', sa.String(255), nullable=False, default=''),
        sa.Column('run_date_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('run_date_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finish_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('export_format', sa.String(10), nullable=True),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_workflow_status', 'sql_workflow', ['status'])
    op.create_index('ix_workflow_engineer', 'sql_workflow', ['engineer_id'])
    op.create_index('ix_workflow_instance', 'sql_workflow', ['instance_id'])
    op.create_index('ix_workflow_tenant', 'sql_workflow', ['tenant_id'])

    # ── sql_workflow_content ──────────────────────────────────
    op.create_table(
        'sql_workflow_content',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('workflow_id', sa.Integer(), sa.ForeignKey('sql_workflow.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('sql_content', sa.Text(), nullable=False),
        sa.Column('review_content', sa.Text(), nullable=False, default=''),
        sa.Column('execute_result', sa.Text(), nullable=False, default=''),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── workflow_audit ────────────────────────────────────────
    op.create_table(
        'workflow_audit',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('workflow_id', sa.Integer(), sa.ForeignKey('sql_workflow.id', ondelete='CASCADE'), nullable=False),
        sa.Column('workflow_type', sa.Integer(), nullable=False),
        sa.Column('workflow_title', sa.String(50), nullable=False, default=''),
        sa.Column('current_audit_auth_group', sa.String(255), nullable=False, default=''),
        sa.Column('current_status', sa.Integer(), nullable=False, default=0),
        sa.Column('audit_auth_groups', sa.String(255), nullable=False, default=''),
        sa.Column('audit_auth_groups_info', sa.Text(), nullable=False, default=''),
        sa.Column('create_user', sa.String(30), nullable=False, default=''),
        sa.Column('create_user_id', sa.Integer(), sa.ForeignKey('sql_users.id')),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_audit_workflow', 'workflow_audit', ['workflow_id'])

    # ── workflow_log ──────────────────────────────────────────
    op.create_table(
        'workflow_log',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('audit_id', sa.Integer(), sa.ForeignKey('workflow_audit.id', ondelete='CASCADE'), nullable=False),
        sa.Column('operator', sa.String(30), nullable=False),
        sa.Column('operator_id', sa.Integer(), sa.ForeignKey('sql_users.id')),
        sa.Column('operation_type', sa.String(20), nullable=False),
        sa.Column('remark', sa.String(500), nullable=False, default=''),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── query_privilege ───────────────────────────────────────
    op.create_table(
        'query_privilege',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('sql_users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('instance_id', sa.Integer(), sa.ForeignKey('sql_instance.id', ondelete='CASCADE'), nullable=False),
        sa.Column('db_name', sa.String(64), nullable=False, default=''),
        sa.Column('table_name', sa.String(64), nullable=False, default=''),
        sa.Column('valid_date', sa.Date(), nullable=False),
        sa.Column('limit_num', sa.Integer(), nullable=False, default=100),
        sa.Column('priv_type', sa.Integer(), nullable=False, default=1),
        sa.Column('is_deleted', sa.Integer(), nullable=False, default=0),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_priv_user_inst_date', 'query_privilege', ['user_id', 'instance_id', 'valid_date', 'is_deleted'])

    # ── query_privilege_apply ──────────────────────────────────
    op.create_table(
        'query_privilege_apply',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('title', sa.String(50), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('sql_users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('instance_id', sa.Integer(), sa.ForeignKey('sql_instance.id', ondelete='CASCADE'), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('db_name', sa.String(64), nullable=False, default=''),
        sa.Column('table_name', sa.String(64), nullable=False, default=''),
        sa.Column('valid_date', sa.Date(), nullable=False),
        sa.Column('limit_num', sa.Integer(), nullable=False, default=100),
        sa.Column('priv_type', sa.Integer(), nullable=False, default=1),
        sa.Column('apply_reason', sa.String(500), nullable=False, default=''),
        sa.Column('status', sa.Integer(), nullable=False, default=0),
        sa.Column('audit_auth_groups', sa.String(255), nullable=False, default=''),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── query_log ─────────────────────────────────────────────
    op.create_table(
        'query_log',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('sql_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('instance_id', sa.Integer(), sa.ForeignKey('sql_instance.id', ondelete='SET NULL'), nullable=True),
        sa.Column('db_name', sa.String(64), nullable=False, default=''),
        sa.Column('sqllog', sa.Text(), nullable=False),
        sa.Column('effect_row', sa.BigInteger(), nullable=False, default=0),
        sa.Column('cost_time_ms', sa.Integer(), nullable=False, default=0),
        sa.Column('priv_check', sa.Boolean(), nullable=False, default=False),
        sa.Column('hit_rule', sa.Boolean(), nullable=False, default=False),
        sa.Column('masking', sa.Boolean(), nullable=False, default=False),
        sa.Column('is_favorite', sa.Boolean(), nullable=False, default=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_qlog_user_date', 'query_log', ['user_id', 'created_at'])
    op.create_index('ix_qlog_instance', 'query_log', ['instance_id'])

    # ── monitor_collect_config ────────────────────────────────
    op.create_table(
        'monitor_collect_config',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('instance_id', sa.Integer(), sa.ForeignKey('sql_instance.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('collect_interval', sa.Integer(), nullable=False, default=60),
        sa.Column('exporter_url', sa.String(500), nullable=False),
        sa.Column('exporter_type', sa.String(50), nullable=False),
        sa.Column('alert_rules_override', sa.JSON(), nullable=False, default={}),
        sa.Column('created_by', sa.String(30), nullable=False, default=''),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── monitor_privilege_apply ───────────────────────────────
    op.create_table(
        'monitor_privilege_apply',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('title', sa.String(50), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('sql_users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('instance_id', sa.Integer(), sa.ForeignKey('sql_instance.id', ondelete='CASCADE'), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('priv_scope', sa.Enum('instance', 'metric_group', name='monitor_priv_scope_enum'), nullable=False, default='instance'),
        sa.Column('metric_groups', sa.String(200), nullable=False, default=''),
        sa.Column('valid_date', sa.Date(), nullable=False),
        sa.Column('apply_reason', sa.String(500), nullable=False, default=''),
        sa.Column('status', sa.Integer(), nullable=False, default=0),
        sa.Column('audit_auth_groups', sa.String(255), nullable=False, default=''),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── monitor_privilege ─────────────────────────────────────
    op.create_table(
        'monitor_privilege',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('apply_id', sa.Integer(), sa.ForeignKey('monitor_privilege_apply.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('sql_users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('instance_id', sa.Integer(), sa.ForeignKey('sql_instance.id', ondelete='CASCADE'), nullable=False),
        sa.Column('priv_scope', sa.String(20), nullable=False, default='instance'),
        sa.Column('metric_groups', sa.String(200), nullable=False, default=''),
        sa.Column('valid_date', sa.Date(), nullable=False),
        sa.Column('is_deleted', sa.Integer(), nullable=False, default=0),
        sa.Column('tenant_id', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_mon_priv_lookup', 'monitor_privilege', ['user_id', 'instance_id', 'valid_date', 'is_deleted'])


def downgrade() -> None:
    op.drop_table('monitor_privilege')
    op.drop_table('monitor_privilege_apply')
    op.drop_table('monitor_collect_config')
    op.drop_table('query_log')
    op.drop_table('query_privilege_apply')
    op.drop_table('query_privilege')
    op.drop_table('workflow_log')
    op.drop_table('workflow_audit')
    op.drop_table('sql_workflow_content')
    op.drop_table('sql_workflow')
    op.drop_table('instance_resource_group')
    op.drop_table('instance_tag')
    op.drop_table('sql_instance')
    op.drop_table('ssh_tunnel')
    op.drop_table('user_permission')
    op.drop_table('user_resource_group')
    op.drop_table('sql_users')
    op.drop_table('resource_group')
    op.drop_table('permission')
    op.execute("DROP TYPE IF EXISTS instance_type_enum")
    op.execute("DROP TYPE IF EXISTS monitor_priv_scope_enum")
