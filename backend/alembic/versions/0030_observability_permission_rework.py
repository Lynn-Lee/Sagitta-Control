"""observability permission rework

Revision ID: 0030_observability_perm
Revises: 0029_native_observability
Create Date: 2026-04-29
"""

import sqlalchemy as sa

from alembic import op


revision = "0030_observability_perm"
down_revision = "0029_native_observability"
branch_labels = None
depends_on = None


NEW_PERMISSIONS = [
    ("menu_observability", "观测中心菜单"),
    ("observability_instance_all", "查看所有实例观测数据"),
    ("observability_session_view", "查看在线与历史会话"),
    ("observability_session_kill", "Kill 会话"),
    ("observability_sql_view", "查看 SQL 洞察"),
    ("observability_sql_analyze", "SQL 执行计划与优化诊断"),
    ("observability_collect_manage", "管理观测采集配置"),
    ("observability_alert_manage", "管理告警规则"),
]

OLD_PERMISSIONS = [
    "menu_monitor",
    "monitor_all_instances",
    "monitor_config_manage",
    "monitor_apply",
    "monitor_review",
    "monitor_alert_manage",
    "menu_ops",
    "process_view",
    "process_kill",
]


def upgrade() -> None:
    conn = op.get_bind()
    for codename, name in NEW_PERMISSIONS:
        conn.execute(
            sa.text(
                """
                INSERT INTO permission (codename, name, tenant_id, created_at, updated_at)
                VALUES (:codename, :name, 1, now(), now())
                ON CONFLICT (codename) DO UPDATE
                SET name = EXCLUDED.name, updated_at = now()
                """
            ),
            {"codename": codename, "name": name},
        )

    conn.execute(sa.text("""
        WITH mapping(old_code, new_code) AS (
            VALUES
                ('menu_monitor', 'menu_observability'),
                ('menu_ops', 'menu_observability'),
                ('menu_ops', 'observability_sql_view'),
                ('menu_ops', 'observability_sql_analyze'),
                ('menu_ops', 'observability_collect_manage'),
                ('process_view', 'observability_session_view'),
                ('process_kill', 'observability_session_kill'),
                ('monitor_all_instances', 'observability_instance_all'),
                ('monitor_config_manage', 'observability_collect_manage'),
                ('monitor_alert_manage', 'observability_alert_manage')
        )
        INSERT INTO role_permission (role_id, permission_id)
        SELECT DISTINCT rp.role_id, new_perm.id
        FROM role_permission rp
        JOIN permission old_perm ON old_perm.id = rp.permission_id
        JOIN mapping m ON m.old_code = old_perm.codename
        JOIN permission new_perm ON new_perm.codename = m.new_code
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permission existing
            WHERE existing.role_id = rp.role_id
              AND existing.permission_id = new_perm.id
        )
    """))

    conn.execute(sa.text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id
        FROM role r
        CROSS JOIN permission p
        WHERE r.name IN ('superadmin', 'dba')
          AND p.codename IN (
            'menu_observability',
            'observability_instance_all',
            'observability_session_view',
            'observability_session_kill',
            'observability_sql_view',
            'observability_sql_analyze',
            'observability_collect_manage',
            'observability_alert_manage'
          )
          AND NOT EXISTS (
              SELECT 1 FROM role_permission rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """))

    conn.execute(sa.text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id
        FROM role r
        CROSS JOIN permission p
        WHERE r.name = 'dba_group'
          AND p.codename IN (
            'menu_observability',
            'observability_session_view',
            'observability_session_kill',
            'observability_sql_view',
            'observability_sql_analyze',
            'observability_collect_manage',
            'observability_alert_manage'
          )
          AND NOT EXISTS (
              SELECT 1 FROM role_permission rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """))

    conn.execute(
        sa.text(
            """
            DELETE FROM role_permission
            WHERE permission_id IN (
                SELECT id FROM permission WHERE codename = ANY(:old_codes)
            )
            """
        ),
        {"old_codes": OLD_PERMISSIONS},
    )
    conn.execute(
        sa.text("DELETE FROM permission WHERE codename = ANY(:old_codes)"),
        {"old_codes": OLD_PERMISSIONS},
    )


def downgrade() -> None:
    conn = op.get_bind()
    restored = [
        ("menu_monitor", "可观测中心菜单"),
        ("monitor_all_instances", "查看所有实例监控"),
        ("monitor_config_manage", "管理采集配置"),
        ("monitor_apply", "申请监控权限"),
        ("monitor_review", "审批监控权限"),
        ("monitor_alert_manage", "管理告警规则"),
        ("menu_ops", "运维工具菜单"),
        ("process_view", "查看会话"),
        ("process_kill", "Kill 会话"),
    ]
    for codename, name in restored:
        conn.execute(
            sa.text(
                """
                INSERT INTO permission (codename, name, tenant_id, created_at, updated_at)
                VALUES (:codename, :name, 1, now(), now())
                ON CONFLICT (codename) DO NOTHING
                """
            ),
            {"codename": codename, "name": name},
        )

    conn.execute(sa.text("""
        WITH mapping(new_code, old_code) AS (
            VALUES
                ('menu_observability', 'menu_monitor'),
                ('observability_instance_all', 'monitor_all_instances'),
                ('observability_session_view', 'process_view'),
                ('observability_session_kill', 'process_kill'),
                ('observability_collect_manage', 'monitor_config_manage'),
                ('observability_alert_manage', 'monitor_alert_manage')
        )
        INSERT INTO role_permission (role_id, permission_id)
        SELECT DISTINCT rp.role_id, old_perm.id
        FROM role_permission rp
        JOIN permission new_perm ON new_perm.id = rp.permission_id
        JOIN mapping m ON m.new_code = new_perm.codename
        JOIN permission old_perm ON old_perm.codename = m.old_code
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permission existing
            WHERE existing.role_id = rp.role_id
              AND existing.permission_id = old_perm.id
        )
    """))

    conn.execute(
        sa.text(
            """
            DELETE FROM role_permission
            WHERE permission_id IN (
                SELECT id FROM permission WHERE codename = ANY(:new_codes)
            )
            """
        ),
        {"new_codes": [code for code, _ in NEW_PERMISSIONS]},
    )
    conn.execute(
        sa.text("DELETE FROM permission WHERE codename = ANY(:new_codes)"),
        {"new_codes": [code for code, _ in NEW_PERMISSIONS]},
    )
