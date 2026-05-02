"""通知身份与投递日志

Revision ID: 0032_notification_delivery
Revises: 0031_sql_activity_collect
Create Date: 2026-04-29
"""

import sqlalchemy as sa

from alembic import op


revision = "0032_notification_delivery"
down_revision = "0031_sql_activity_collect"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sql_users",
        sa.Column("dingtalk_user_id", sa.String(length=100), nullable=False, server_default="", comment="钉钉用户ID"),
    )
    op.add_column(
        "sql_users",
        sa.Column("feishu_open_id", sa.String(length=100), nullable=False, server_default="", comment="飞书 Open ID"),
    )
    op.add_column(
        "sql_users",
        sa.Column("wecom_userid", sa.String(length=100), nullable=False, server_default="", comment="企业微信 UserID"),
    )
    op.alter_column("sql_users", "dingtalk_user_id", server_default=None)
    op.alter_column("sql_users", "feishu_open_id", server_default=None)
    op.alter_column("sql_users", "wecom_userid", server_default=None)

    op.create_table(
        "notification_delivery_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False, comment="通知事件"),
        sa.Column("subject_type", sa.String(length=30), nullable=False, server_default="", comment="对象类型"),
        sa.Column("subject_id", sa.Integer(), nullable=False, server_default="0", comment="对象ID"),
        sa.Column("channel", sa.String(length=20), nullable=False, comment="通知渠道"),
        sa.Column("recipient_user_id", sa.Integer(), nullable=True, comment="收件用户ID"),
        sa.Column("recipient", sa.String(length=200), nullable=False, server_default="", comment="收件地址/外部ID"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending", comment="sent/failed/skipped"),
        sa.Column("error", sa.Text(), nullable=False, server_default="", comment="失败原因"),
        sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1", comment="租户ID（SaaS预留）"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["sql_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notify_event", "notification_delivery_log", ["event_type"])
    op.create_index("ix_notify_subject", "notification_delivery_log", ["subject_type", "subject_id"])
    op.create_index("ix_notify_user", "notification_delivery_log", ["recipient_user_id"])
    op.create_index("ix_notify_status", "notification_delivery_log", ["status"])
    op.create_index("ix_notify_tenant", "notification_delivery_log", ["tenant_id"])
    op.alter_column("notification_delivery_log", "subject_type", server_default=None)
    op.alter_column("notification_delivery_log", "subject_id", server_default=None)
    op.alter_column("notification_delivery_log", "recipient", server_default=None)
    op.alter_column("notification_delivery_log", "status", server_default=None)
    op.alter_column("notification_delivery_log", "error", server_default=None)
    op.alter_column("notification_delivery_log", "tenant_id", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_notify_tenant", table_name="notification_delivery_log")
    op.drop_index("ix_notify_status", table_name="notification_delivery_log")
    op.drop_index("ix_notify_user", table_name="notification_delivery_log")
    op.drop_index("ix_notify_subject", table_name="notification_delivery_log")
    op.drop_index("ix_notify_event", table_name="notification_delivery_log")
    op.drop_table("notification_delivery_log")
    op.drop_column("sql_users", "wecom_userid")
    op.drop_column("sql_users", "feishu_open_id")
    op.drop_column("sql_users", "dingtalk_user_id")
