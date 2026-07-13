"""用户部署运营支持

Revision ID: 0037_commercial_operations
Revises: 0036_create_masking_rule
Create Date: 2026-05-28
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0037_commercial_operations"
down_revision = "0036_create_masking_rule"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("delivery_acceptance_run"):
        op.create_table(
            "delivery_acceptance_run",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="success"),
            sa.Column("options", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("report_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("report_markdown", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_delivery_run_status", "delivery_acceptance_run", ["status"])
        op.create_index("ix_delivery_run_tenant", "delivery_acceptance_run", ["tenant_id"])

    if not _has_table("diagnostic_bundle"):
        op.create_table(
            "diagnostic_bundle",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="success"),
            sa.Column("bundle_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_by", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_diagnostic_bundle_status", "diagnostic_bundle", ["status"])
        op.create_index("ix_diagnostic_bundle_tenant", "diagnostic_bundle", ["tenant_id"])

    if not _has_table("monitor_alert_event"):
        op.create_table(
            "monitor_alert_event",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("instance_id", sa.Integer(), nullable=False),
            sa.Column("rule_key", sa.String(length=80), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False, server_default="warning"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="firing"),
            sa.Column("title", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("message", sa.Text(), nullable=False, server_default=""),
            sa.Column("metric_value", sa.Float(), nullable=True),
            sa.Column("threshold", sa.Float(), nullable=True),
            sa.Column("snapshot_id", sa.Integer(), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("acknowledged_by", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("silenced_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_by", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("close_reason", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("extra", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["instance_id"], ["sql_instance.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["snapshot_id"], ["monitor_metric_snapshot.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_alert_event_instance_status", "monitor_alert_event", ["instance_id", "status"])
        op.create_index("ix_alert_event_rule_status", "monitor_alert_event", ["rule_key", "status"])
        op.create_index("ix_alert_event_tenant", "monitor_alert_event", ["tenant_id"])


def downgrade() -> None:
    if _has_table("monitor_alert_event"):
        op.drop_index("ix_alert_event_tenant", table_name="monitor_alert_event")
        op.drop_index("ix_alert_event_rule_status", table_name="monitor_alert_event")
        op.drop_index("ix_alert_event_instance_status", table_name="monitor_alert_event")
        op.drop_table("monitor_alert_event")
    if _has_table("diagnostic_bundle"):
        op.drop_index("ix_diagnostic_bundle_tenant", table_name="diagnostic_bundle")
        op.drop_index("ix_diagnostic_bundle_status", table_name="diagnostic_bundle")
        op.drop_table("diagnostic_bundle")
    if _has_table("delivery_acceptance_run"):
        op.drop_index("ix_delivery_run_tenant", table_name="delivery_acceptance_run")
        op.drop_index("ix_delivery_run_status", table_name="delivery_acceptance_run")
        op.drop_table("delivery_acceptance_run")
