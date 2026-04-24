"""backfill query log snapshot fields

Revision ID: 0018_qlog_snapshot_backfill
Revises: 0017_query_log_history_audit
Create Date: 2026-04-23 18:05:00
"""

from alembic import op


revision = "0018_qlog_snapshot_backfill"
down_revision = "0017_query_log_history_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE query_log q
        SET username = u.username
        FROM sql_users u
        WHERE q.user_id = u.id
          AND COALESCE(q.username, '') = ''
        """
    )
    op.execute(
        """
        UPDATE query_log q
        SET instance_name = i.instance_name,
            db_type = i.db_type
        FROM sql_instance i
        WHERE q.instance_id = i.id
          AND (COALESCE(q.instance_name, '') = '' OR COALESCE(q.db_type, '') = '')
        """
    )


def downgrade() -> None:
    pass
