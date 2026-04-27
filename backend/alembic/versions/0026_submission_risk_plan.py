"""add submission risk plan fields

Revision ID: 0026_submission_risk_plan
Revises: 0025_session_duration_fields
Create Date: 2026-04-26 00:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "0026_submission_risk_plan"
down_revision = "0025_session_duration_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sql_workflow_content", sa.Column("risk_plan", sa.Text(), nullable=False, server_default="", comment="风险预案JSON"))
    op.add_column("sql_workflow_content", sa.Column("risk_remark", sa.String(length=500), nullable=False, server_default="", comment="申请人风险说明"))

    op.add_column("query_privilege_apply", sa.Column("risk_level", sa.String(length=20), nullable=False, server_default="", comment="风险等级"))
    op.add_column("query_privilege_apply", sa.Column("risk_summary", sa.String(length=500), nullable=False, server_default="", comment="风险摘要"))
    op.add_column("query_privilege_apply", sa.Column("risk_remark", sa.String(length=500), nullable=False, server_default="", comment="申请人风险说明"))

    op.add_column("archive_job", sa.Column("risk_plan", sa.Text(), nullable=False, server_default="", comment="风险预案JSON"))
    op.add_column("archive_job", sa.Column("risk_level", sa.String(length=20), nullable=False, server_default="", comment="风险等级"))
    op.add_column("archive_job", sa.Column("risk_summary", sa.String(length=500), nullable=False, server_default="", comment="风险摘要"))
    op.add_column("archive_job", sa.Column("risk_remark", sa.String(length=500), nullable=False, server_default="", comment="申请人风险说明"))

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

    op.drop_column("archive_job", "risk_remark")
    op.drop_column("archive_job", "risk_summary")
    op.drop_column("archive_job", "risk_level")
    op.drop_column("archive_job", "risk_plan")

    op.drop_column("query_privilege_apply", "risk_remark")
    op.drop_column("query_privilege_apply", "risk_summary")
    op.drop_column("query_privilege_apply", "risk_level")

    op.drop_column("sql_workflow_content", "risk_remark")
    op.drop_column("sql_workflow_content", "risk_plan")
