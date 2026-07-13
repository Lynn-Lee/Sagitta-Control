"""站内通知收件箱

Revision ID: 0038_system_notification
Revises: 0037_commercial_operations
Create Date: 2026-05-31
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0038_system_notification"
down_revision = "0037_commercial_operations"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("system_notification"):
        return
    op.create_table(
        "system_notification",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False, comment="收件用户ID"),
        sa.Column("event_type", sa.String(length=50), nullable=False, comment="通知事件"),
        sa.Column("subject_type", sa.String(length=30), nullable=False, server_default="", comment="对象类型"),
        sa.Column("subject_id", sa.Integer(), nullable=False, server_default="0", comment="对象ID"),
        sa.Column("title", sa.String(length=200), nullable=False, server_default="", comment="通知标题"),
        sa.Column("content", sa.Text(), nullable=False, server_default="", comment="通知内容"),
        sa.Column("detail_path", sa.String(length=500), nullable=False, server_default="", comment="跳转路径"),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false"), comment="是否已读"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True, comment="已读时间"),
        sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1", comment="租户ID（SaaS预留）"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["sql_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sys_notify_recipient_read", "system_notification", ["recipient_user_id", "is_read"])
    op.create_index("ix_sys_notify_subject", "system_notification", ["subject_type", "subject_id"])
    op.create_index("ix_sys_notify_event", "system_notification", ["event_type"])
    op.create_index("ix_sys_notify_tenant", "system_notification", ["tenant_id"])
    op.alter_column("system_notification", "subject_type", server_default=None)
    op.alter_column("system_notification", "subject_id", server_default=None)
    op.alter_column("system_notification", "title", server_default=None)
    op.alter_column("system_notification", "content", server_default=None)
    op.alter_column("system_notification", "detail_path", server_default=None)
    op.alter_column("system_notification", "is_read", server_default=None)
    op.alter_column("system_notification", "tenant_id", server_default=None)


def downgrade() -> None:
    if not _has_table("system_notification"):
        return
    op.drop_index("ix_sys_notify_tenant", table_name="system_notification")
    op.drop_index("ix_sys_notify_event", table_name="system_notification")
    op.drop_index("ix_sys_notify_subject", table_name="system_notification")
    op.drop_index("ix_sys_notify_recipient_read", table_name="system_notification")
    op.drop_table("system_notification")
