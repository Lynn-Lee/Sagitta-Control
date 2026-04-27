"""split archive execute permission

Revision ID: 0028_archive_execute_perm
Revises: 0027_high_risk_sql_perm
Create Date: 2026-04-27 00:00:00
"""

import sqlalchemy as sa

from alembic import op


revision = "0028_archive_execute_perm"
down_revision = "0027_high_risk_sql_perm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO permission (codename, name, tenant_id, created_at, updated_at)
        VALUES ('archive_execute', '执行数据归档', 1, now(), now())
        ON CONFLICT (codename) DO NOTHING
    """))
    conn.execute(sa.text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id
        FROM role r
        CROSS JOIN permission p
        WHERE r.name IN ('superadmin', 'dba', 'dba_group')
          AND p.codename = 'archive_execute'
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
        WHERE r.name = 'developer'
          AND p.codename = 'archive_apply'
          AND NOT EXISTS (
              SELECT 1 FROM role_permission rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        DELETE FROM role_permission
        WHERE permission_id IN (
            SELECT id FROM permission WHERE codename = 'archive_execute'
        )
    """))
    conn.execute(sa.text("DELETE FROM permission WHERE codename = 'archive_execute'"))
