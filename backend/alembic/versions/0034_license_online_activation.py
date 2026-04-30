"""license online activation metadata

Revision ID: 0034_license_online_activation
Revises: 0033_license_record
Create Date: 2026-04-30
"""

import sqlalchemy as sa

from alembic import op


revision = "0034_license_online_activation"
down_revision = "0033_license_record"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("license_record", sa.Column("activation_code", sa.String(length=100), nullable=False, server_default="", comment="激活码"))
    op.add_column("license_record", sa.Column("activation_id", sa.String(length=100), nullable=False, server_default="", comment="在线激活 ID"))
    op.add_column("license_record", sa.Column("server_url", sa.String(length=500), nullable=False, server_default="", comment="授权服务器地址"))
    op.add_column("license_record", sa.Column("remote_status", sa.String(length=20), nullable=False, server_default="", comment="授权服务器返回状态"))
    op.add_column("license_record", sa.Column("last_online_check_at", sa.DateTime(timezone=True), nullable=True, comment="最后联网校验时间"))
    op.create_index("ix_license_activation", "license_record", ["activation_id"])
    op.create_index("ix_license_remote_status", "license_record", ["remote_status"])
    for column in ("activation_code", "activation_id", "server_url", "remote_status"):
        op.alter_column("license_record", column, server_default=None)


def downgrade() -> None:
    op.drop_index("ix_license_remote_status", table_name="license_record")
    op.drop_index("ix_license_activation", table_name="license_record")
    op.drop_column("license_record", "last_online_check_at")
    op.drop_column("license_record", "remote_status")
    op.drop_column("license_record", "server_url")
    op.drop_column("license_record", "activation_id")
    op.drop_column("license_record", "activation_code")
