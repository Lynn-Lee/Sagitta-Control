"""query privilege apply add approval flow fields

Revision ID: 0010_query_priv_apply_flow
Revises: 0009
Create Date: 2026-04-17 15:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_query_priv_apply_flow"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "query_privilege_apply",
        sa.Column("flow_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "query_privilege_apply",
        sa.Column("audit_auth_groups_info", sa.Text(), nullable=False, server_default=""),
    )
    op.create_foreign_key(
        "fk_qpa_flow_id",
        "query_privilege_apply",
        "approval_flow",
        ["flow_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_qpa_flow_id", "query_privilege_apply", ["flow_id"])
    op.alter_column("query_privilege_apply", "audit_auth_groups_info", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_qpa_flow_id", "query_privilege_apply")
    op.drop_constraint("fk_qpa_flow_id", "query_privilege_apply", type_="foreignkey")
    op.drop_column("query_privilege_apply", "audit_auth_groups_info")
    op.drop_column("query_privilege_apply", "flow_id")
