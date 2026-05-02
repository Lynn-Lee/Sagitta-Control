"""修复 totp_secret 字段长度：100 -> 500

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-23
"""
import sqlalchemy as sa

from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('sql_users', 'totp_secret',
        existing_type=sa.String(100),
        type_=sa.String(500),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column('sql_users', 'totp_secret',
        existing_type=sa.String(500),
        type_=sa.String(100),
        existing_nullable=True,
    )
