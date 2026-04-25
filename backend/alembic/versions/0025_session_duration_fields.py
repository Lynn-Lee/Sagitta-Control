"""add explicit session duration fields

Revision ID: 0025_session_duration_fields
Revises: 0024_session_duration_ms
Create Date: 2026-04-25 16:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "0025_session_duration_fields"
down_revision = "0024_session_duration_ms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "session_snapshot",
        sa.Column("connection_age_ms", sa.BigInteger(), nullable=True, comment="连接/会话存活时长(毫秒)"),
    )
    op.add_column(
        "session_snapshot",
        sa.Column("state_duration_ms", sa.BigInteger(), nullable=True, comment="当前状态持续时长(毫秒)"),
    )
    op.add_column(
        "session_snapshot",
        sa.Column("active_duration_ms", sa.BigInteger(), nullable=True, comment="当前活动/操作持续时长(毫秒)"),
    )
    op.add_column(
        "session_snapshot",
        sa.Column("transaction_age_ms", sa.BigInteger(), nullable=True, comment="当前事务持续时长(毫秒)"),
    )
    op.add_column(
        "session_snapshot",
        sa.Column("duration_source", sa.String(length=64), nullable=False, server_default="", comment="时长来源说明"),
    )
    op.execute(
        """
        UPDATE session_snapshot
        SET state_duration_ms = duration_ms,
            duration_source = CASE WHEN duration_ms > 0 THEN 'legacy_duration_ms' ELSE '' END
        """
    )


def downgrade() -> None:
    op.drop_column("session_snapshot", "duration_source")
    op.drop_column("session_snapshot", "transaction_age_ms")
    op.drop_column("session_snapshot", "active_duration_ms")
    op.drop_column("session_snapshot", "state_duration_ms")
    op.drop_column("session_snapshot", "connection_age_ms")
