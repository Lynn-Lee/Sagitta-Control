"""seed high-risk SQL submit permission

Revision ID: 0027_high_risk_sql_perm
Revises: 0026_submission_risk_plan
Create Date: 2026-04-26 00:00:00
"""

import sqlalchemy as sa

from alembic import op


revision = "0027_high_risk_sql_perm"
down_revision = "0026_submission_risk_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO permission (codename, name, tenant_id, created_at, updated_at)
        VALUES ('sql_submit_high_risk', '提交高危 SQL 工单', 1, now(), now())
        ON CONFLICT (codename) DO NOTHING
    """))
    conn.execute(sa.text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id
        FROM role r
        CROSS JOIN permission p
        WHERE r.name IN ('superadmin', 'dba', 'dba_group')
          AND p.codename = 'sql_submit_high_risk'
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
            SELECT id FROM permission WHERE codename = 'sql_submit_high_risk'
        )
    """))
    conn.execute(sa.text("DELETE FROM permission WHERE codename = 'sql_submit_high_risk'"))
