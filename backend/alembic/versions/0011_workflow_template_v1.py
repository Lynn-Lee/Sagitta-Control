"""workflow template v1 fields

Revision ID: 0011_workflow_template_v1
Revises: 0010_query_priv_apply_flow
Create Date: 2026-04-18 15:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_workflow_template_v1"
down_revision = "0010_query_priv_apply_flow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_template",
        sa.Column("category", sa.String(length=30), nullable=False, server_default="other"),
    )
    op.add_column(
        "workflow_template",
        sa.Column("scene_desc", sa.String(length=300), nullable=False, server_default=""),
    )
    op.add_column(
        "workflow_template",
        sa.Column("risk_hint", sa.String(length=300), nullable=False, server_default=""),
    )
    op.add_column(
        "workflow_template",
        sa.Column("rollback_hint", sa.String(length=300), nullable=False, server_default=""),
    )
    op.add_column(
        "workflow_template",
        sa.Column("flow_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "workflow_template",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_index("ix_tmpl_category", "workflow_template", ["category"])
    op.create_index("ix_tmpl_active", "workflow_template", ["is_active"])
    op.create_foreign_key(
        "fk_workflow_template_flow_id",
        "workflow_template",
        "approval_flow",
        ["flow_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column("workflow_template", "category", server_default=None)
    op.alter_column("workflow_template", "scene_desc", server_default=None)
    op.alter_column("workflow_template", "risk_hint", server_default=None)
    op.alter_column("workflow_template", "rollback_hint", server_default=None)
    op.alter_column("workflow_template", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_workflow_template_flow_id", "workflow_template", type_="foreignkey")
    op.drop_index("ix_tmpl_active", table_name="workflow_template")
    op.drop_index("ix_tmpl_category", table_name="workflow_template")
    op.drop_column("workflow_template", "is_active")
    op.drop_column("workflow_template", "flow_id")
    op.drop_column("workflow_template", "rollback_hint")
    op.drop_column("workflow_template", "risk_hint")
    op.drop_column("workflow_template", "scene_desc")
    op.drop_column("workflow_template", "category")
