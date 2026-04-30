"""license record

Revision ID: 0033_license_record
Revises: 0032_notification_delivery
Create Date: 2026-04-30
"""

import sqlalchemy as sa

from alembic import op


revision = "0033_license_record"
down_revision = "0032_notification_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "license_record",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="trial", comment="trial/import/online"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="trial", comment="trial/licensed/invalid/expired"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true"), comment="是否当前授权"),
        sa.Column("raw_license", sa.Text(), nullable=False, server_default="", comment="原始 license JSON"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json"), comment="License payload"),
        sa.Column("signature", sa.Text(), nullable=False, server_default="", comment="License 签名"),
        sa.Column("license_id", sa.String(length=100), nullable=False, server_default="", comment="License ID"),
        sa.Column("customer_id", sa.String(length=100), nullable=False, server_default="", comment="客户 ID"),
        sa.Column("company_name", sa.String(length=200), nullable=False, server_default="", comment="客户名称"),
        sa.Column("edition", sa.String(length=50), nullable=False, server_default="trial", comment="版本"),
        sa.Column("features", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json"), comment="授权功能"),
        sa.Column("limits", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json"), comment="授权额度"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True, comment="签发时间"),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=True, comment="生效时间"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True, comment="过期时间"),
        sa.Column("last_check_status", sa.String(length=20), nullable=False, server_default="ok", comment="最后检查状态"),
        sa.Column("last_check_reason", sa.String(length=500), nullable=False, server_default="", comment="最后检查原因"),
        sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1", comment="租户ID（SaaS预留）"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_license_current", "license_record", ["is_current"])
    op.create_index("ix_license_status", "license_record", ["status"])
    op.create_index("ix_license_customer", "license_record", ["customer_id"])
    op.create_index("ix_license_expires", "license_record", ["expires_at"])
    op.create_index("ix_license_tenant", "license_record", ["tenant_id"])

    for column in (
        "source",
        "status",
        "is_current",
        "raw_license",
        "payload",
        "signature",
        "license_id",
        "customer_id",
        "company_name",
        "edition",
        "features",
        "limits",
        "last_check_status",
        "last_check_reason",
        "tenant_id",
    ):
        op.alter_column("license_record", column, server_default=None)


def downgrade() -> None:
    op.drop_index("ix_license_tenant", table_name="license_record")
    op.drop_index("ix_license_expires", table_name="license_record")
    op.drop_index("ix_license_customer", table_name="license_record")
    op.drop_index("ix_license_status", table_name="license_record")
    op.drop_index("ix_license_current", table_name="license_record")
    op.drop_table("license_record")
