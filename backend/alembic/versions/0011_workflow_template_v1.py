"""workflow template v1 fields

Revision ID: 0011_workflow_template_v1
Revises: 0010_query_priv_apply_flow
Create Date: 2026-04-18 15:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0011_workflow_template_v1"
down_revision = "0010_query_priv_apply_flow"
branch_labels = None
depends_on = None


TABLE_NAME = "workflow_template"
FK_NAME = "fk_workflow_template_flow_id"
INDEX_CATEGORY = "ix_tmpl_category"
INDEX_ACTIVE = "ix_tmpl_active"


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _foreign_key_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {fk["name"] for fk in inspector.get_foreign_keys(table_name) if fk.get("name")}


def _create_workflow_template_table() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_name", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False, server_default="other"),
        sa.Column("description", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("scene_desc", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("risk_hint", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("rollback_hint", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("instance_id", sa.Integer(), nullable=True),
        sa.Column("db_name", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("flow_id", sa.Integer(), nullable=True),
        sa.Column("sql_content", sa.Text(), nullable=False),
        sa.Column("syntax_type", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("visibility", sa.String(length=10), nullable=False, server_default="public"),
        sa.Column("created_by", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("created_by_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _table_exists(inspector, TABLE_NAME):
        _create_workflow_template_table()
        inspector = inspect(bind)
    else:
        columns = _column_names(inspector, TABLE_NAME)
        missing_columns: list[tuple[str, sa.Column]] = [
            ("category", sa.Column("category", sa.String(length=30), nullable=False, server_default="other")),
            ("scene_desc", sa.Column("scene_desc", sa.String(length=300), nullable=False, server_default="")),
            ("risk_hint", sa.Column("risk_hint", sa.String(length=300), nullable=False, server_default="")),
            ("rollback_hint", sa.Column("rollback_hint", sa.String(length=300), nullable=False, server_default="")),
            ("flow_id", sa.Column("flow_id", sa.Integer(), nullable=True)),
            ("is_active", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true"))),
        ]
        for column_name, column in missing_columns:
            if column_name not in columns:
                op.add_column(TABLE_NAME, column)

        columns = _column_names(inspector, TABLE_NAME)
        if "category" in columns:
            op.alter_column(TABLE_NAME, "category", server_default=None)
        if "scene_desc" in columns:
            op.alter_column(TABLE_NAME, "scene_desc", server_default=None)
        if "risk_hint" in columns:
            op.alter_column(TABLE_NAME, "risk_hint", server_default=None)
        if "rollback_hint" in columns:
            op.alter_column(TABLE_NAME, "rollback_hint", server_default=None)
        if "is_active" in columns:
            op.alter_column(TABLE_NAME, "is_active", server_default=None)

        inspector = inspect(bind)

    indexes = _index_names(inspector, TABLE_NAME)
    if INDEX_CATEGORY not in indexes:
        op.create_index(INDEX_CATEGORY, TABLE_NAME, ["category"])
    if INDEX_ACTIVE not in indexes:
        op.create_index(INDEX_ACTIVE, TABLE_NAME, ["is_active"])

    foreign_keys = _foreign_key_names(inspector, TABLE_NAME)
    if FK_NAME not in foreign_keys:
        op.create_foreign_key(
            FK_NAME,
            TABLE_NAME,
            "approval_flow",
            ["flow_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.alter_column(TABLE_NAME, "category", server_default=None)
    op.alter_column(TABLE_NAME, "scene_desc", server_default=None)
    op.alter_column(TABLE_NAME, "risk_hint", server_default=None)
    op.alter_column(TABLE_NAME, "rollback_hint", server_default=None)
    op.alter_column(TABLE_NAME, "is_active", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not _table_exists(inspector, TABLE_NAME):
        return

    foreign_keys = _foreign_key_names(inspector, TABLE_NAME)
    if FK_NAME in foreign_keys:
        op.drop_constraint(FK_NAME, TABLE_NAME, type_="foreignkey")

    indexes = _index_names(inspector, TABLE_NAME)
    if INDEX_ACTIVE in indexes:
        op.drop_index(INDEX_ACTIVE, table_name=TABLE_NAME)
    if INDEX_CATEGORY in indexes:
        op.drop_index(INDEX_CATEGORY, table_name=TABLE_NAME)

    columns = _column_names(inspector, TABLE_NAME)
    for column_name in ["is_active", "flow_id", "rollback_hint", "risk_hint", "scene_desc", "category"]:
        if column_name in columns:
            op.drop_column(TABLE_NAME, column_name)
