"""Phase 4：删除旧版 user_permission 和 user_resource_group 表。

In v2, permissions are managed through role_permission (Role → Permission),
and resource group access is through group_resource_group (UserGroup → ResourceGroup).
These legacy M2M tables are no longer needed.

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-13
"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("user_resource_group")
    op.drop_table("user_permission")


def downgrade() -> None:
    op.create_table(
        "user_permission",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("sql_users.id", ondelete="CASCADE")),
        sa.Column(
            "permission_id", sa.Integer(), sa.ForeignKey("permission.id", ondelete="CASCADE")
        ),
    )
    op.create_table(
        "user_resource_group",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("sql_users.id", ondelete="CASCADE")),
        sa.Column(
            "resource_group_id",
            sa.Integer(),
            sa.ForeignKey("resource_group.id", ondelete="CASCADE"),
        ),
    )
