"""backfill query privilege revoke audit fields

Revision ID: 0015_priv_revoke_backfill
Revises: 0014_query_priv_revoke_audit
Create Date: 2026-04-21 13:10:00
"""

from alembic import op


revision = "0015_priv_revoke_backfill"
down_revision = "0014_query_priv_revoke_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE query_privilege
        SET
            revoked_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP),
            revoked_by_name = COALESCE(revoked_by_name, '系统/历史数据'),
            revoke_reason = COALESCE(revoke_reason, '历史软删除记录兼容回填')
        WHERE is_deleted = 1
          AND revoked_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE query_privilege
        SET
            revoked_at = NULL,
            revoked_by_name = NULL,
            revoke_reason = NULL
        WHERE is_deleted = 1
          AND revoked_by_id IS NULL
          AND revoked_by_name = '系统/历史数据'
          AND revoke_reason = '历史软删除记录兼容回填'
        """
    )
