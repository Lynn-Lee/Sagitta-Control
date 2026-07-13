"""创建脱敏规则表

Revision ID: 0036_create_masking_rule
Revises: 0035_license_deployment_fingerprint
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0036_create_masking_rule"
down_revision = "0035_license_deployment_fingerprint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "masking_rule" in inspector.get_table_names():
        return

    op.create_table(
        "masking_rule",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_name", sa.String(length=50), nullable=False, comment="规则名称"),
        sa.Column("description", sa.String(length=200), nullable=False, server_default="", comment="规则说明"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true(), comment="是否启用"),
        sa.Column("instance_id", sa.Integer(), nullable=True, comment="适用实例ID，NULL=所有实例"),
        sa.Column("db_name", sa.String(length=64), nullable=False, server_default="*", comment="数据库名，*=所有"),
        sa.Column("table_name", sa.String(length=64), nullable=False, server_default="*", comment="表名，*=所有"),
        sa.Column("column_name", sa.String(length=64), nullable=False, comment="列名（支持*通配）"),
        sa.Column("rule_type", sa.String(length=20), nullable=False, comment="规则类型"),
        sa.Column("rule_regex", sa.String(length=500), nullable=False, server_default="", comment="自定义正则表达式"),
        sa.Column("rule_regex_replace", sa.String(length=100), nullable=False, server_default="***", comment="替换字符串"),
        sa.Column("hide_group", sa.Integer(), nullable=False, server_default="0", comment="隐藏正则分组序号"),
        sa.Column("created_by", sa.String(length=30), nullable=False, server_default="", comment="创建人"),
        sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1", comment="租户ID（SaaS预留）"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_masking_active", "masking_rule", ["is_active"])
    op.create_index("ix_masking_instance", "masking_rule", ["instance_id"])
    op.create_index("ix_masking_tenant", "masking_rule", ["tenant_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "masking_rule" not in inspector.get_table_names():
        return

    op.drop_index("ix_masking_tenant", table_name="masking_rule")
    op.drop_index("ix_masking_instance", table_name="masking_rule")
    op.drop_index("ix_masking_active", table_name="masking_rule")
    op.drop_table("masking_rule")
