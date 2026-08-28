"""社区版超额实例挂起标记

Revision ID: 0039_instance_license_suspended
Revises: 0038_system_notification
Create Date: 2026-08-21
"""

import sqlalchemy as sa

from alembic import op

revision = "0039_instance_license_suspended"
down_revision = "0038_system_notification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sql_instance",
        sa.Column(
            "license_suspended",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="是否因超出 License 额度被挂起",
        ),
    )


def downgrade() -> None:
    op.drop_column("sql_instance", "license_suspended")
