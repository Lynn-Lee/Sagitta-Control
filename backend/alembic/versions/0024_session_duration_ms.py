"""add session snapshot duration milliseconds

Revision ID: 0024_session_duration_ms
Revises: 0023_archive_jobs
Create Date: 2026-04-25 00:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "0024_session_duration_ms"
down_revision = "0023_archive_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "session_snapshot",
        sa.Column(
            "duration_ms",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
            comment="运行耗时(毫秒)",
        ),
    )
    op.execute("UPDATE session_snapshot SET duration_ms = COALESCE(time_seconds, 0) * 1000")


def downgrade() -> None:
    op.drop_column("session_snapshot", "duration_ms")
