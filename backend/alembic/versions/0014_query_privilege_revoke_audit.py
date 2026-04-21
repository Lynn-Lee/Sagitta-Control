"""add query privilege revoke audit fields

Revision ID: 0014_query_priv_revoke_audit
Revises: 0013_user_password_policy
Create Date: 2026-04-21 12:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_query_priv_revoke_audit"
down_revision = "0013_user_password_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "query_privilege",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True, comment="撤销时间"),
    )
    op.add_column(
        "query_privilege",
        sa.Column("revoked_by_id", sa.Integer(), nullable=True, comment="撤销人ID"),
    )
    op.add_column(
        "query_privilege",
        sa.Column("revoked_by_name", sa.String(100), nullable=True, comment="撤销人名称"),
    )
    op.add_column(
        "query_privilege",
        sa.Column("revoke_reason", sa.String(500), nullable=True, comment="撤销原因"),
    )
    op.create_index("ix_priv_revoked_at", "query_privilege", ["revoked_at"])
    op.create_foreign_key(
        "fk_query_privilege_revoked_by",
        "query_privilege",
        "sql_users",
        ["revoked_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_query_privilege_revoked_by", "query_privilege", type_="foreignkey")
    op.drop_index("ix_priv_revoked_at", table_name="query_privilege")
    op.drop_column("query_privilege", "revoke_reason")
    op.drop_column("query_privilege", "revoked_by_name")
    op.drop_column("query_privilege", "revoked_by_id")
    op.drop_column("query_privilege", "revoked_at")
