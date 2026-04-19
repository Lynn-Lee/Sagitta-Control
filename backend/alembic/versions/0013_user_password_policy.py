"""add password_changed_at for password expiry policy

Revision ID: 0013_user_password_policy
Revises: 0012_workflow_templates_seed
Create Date: 2026-04-19 10:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_user_password_policy"
down_revision = "0012_workflow_templates_seed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sql_users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE sql_users
            SET password_changed_at = COALESCE(created_at, NOW())
            WHERE password_changed_at IS NULL
            """
        )
    )
    op.alter_column("sql_users", "password_changed_at", nullable=False)


def downgrade() -> None:
    op.drop_column("sql_users", "password_changed_at")
