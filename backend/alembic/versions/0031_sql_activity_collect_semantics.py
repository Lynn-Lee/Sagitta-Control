"""sql activity collection semantics

Revision ID: 0031_sql_activity_collect
Revises: 0030_observability_perm
Create Date: 2026-04-29
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision = "0031_sql_activity_collect"
down_revision = "0030_observability_perm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "slow_query_config",
        sa.Column(
            "last_collect_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="最近采集来源",
        ),
    )
    op.add_column(
        "slow_query_config",
        sa.Column(
            "last_collect_message",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="最近采集说明",
        ),
    )
    op.execute(
        """
        UPDATE slow_query_config cfg
        SET last_collect_status = CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM slow_query_log log
                    WHERE log.instance_id = cfg.instance_id
                )
                THEN 'success'
                ELSE 'never'
            END,
            last_collect_error = '',
            last_collect_sources = CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM slow_query_log log
                    WHERE log.instance_id = cfg.instance_id
                )
                THEN '["platform_history"]'::jsonb
                ELSE '[]'::jsonb
            END,
            last_collect_message = CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM slow_query_log log
                    WHERE log.instance_id = cfg.instance_id
                )
                THEN '平台历史'
                ELSE ''
            END
        WHERE last_collect_status = 'unsupported'
           OR last_collect_error LIKE '%暂不支持原生慢日志采集%'
        """
    )
    op.alter_column("slow_query_config", "last_collect_sources", server_default=None)
    op.alter_column("slow_query_config", "last_collect_message", server_default=None)


def downgrade() -> None:
    op.drop_column("slow_query_config", "last_collect_message")
    op.drop_column("slow_query_config", "last_collect_sources")
