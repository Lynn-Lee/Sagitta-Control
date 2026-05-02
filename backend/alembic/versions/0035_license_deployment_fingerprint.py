"""License 部署指纹

Revision ID: 0035_license_deployment_fingerprint
Revises: 0034_license_online_activation
Create Date: 2026-05-02
"""

import sqlalchemy as sa

from alembic import op


revision = "0035_license_deployment_fingerprint"
down_revision = "0034_license_online_activation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "license_record",
        sa.Column("deployment_fingerprint", sa.String(length=100), nullable=False, server_default="", comment="部署指纹"),
    )
    op.create_index("ix_license_deployment_fingerprint", "license_record", ["deployment_fingerprint"])
    op.alter_column("license_record", "deployment_fingerprint", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_license_deployment_fingerprint", table_name="license_record")
    op.drop_column("license_record", "deployment_fingerprint")
