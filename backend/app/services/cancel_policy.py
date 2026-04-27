"""Shared application-cancel policy helpers."""
from __future__ import annotations

import json
from typing import Any

from app.models.workflow import AuditStatus


class ApplicationCancelPolicy:
    """Rules for canceling an application before any approval node acts."""

    @staticmethod
    def load_nodes(raw: str | None) -> list[dict[str, Any]]:
        try:
            data = json.loads(raw or "[]")
        except Exception:
            return []
        return data if isinstance(data, list) else []

    @staticmethod
    def has_operated_node(nodes: list[dict[str, Any]]) -> bool:
        return any(node.get("status") != AuditStatus.PENDING for node in nodes)

    @staticmethod
    def can_cancel_before_approval(
        *,
        applicant_id: int | None = None,
        applicant_username: str | None = None,
        operator: dict,
        status: int | str,
        pending_status: int | str,
        nodes: list[dict[str, Any]],
    ) -> bool:
        if status != pending_status:
            return False
        if not operator.get("is_superuser"):
            operator_id = operator.get("id")
            operator_username = operator.get("username")
            if applicant_id is not None:
                if operator_id != applicant_id:
                    return False
            elif applicant_username is not None and operator_username != applicant_username:
                return False
        return not ApplicationCancelPolicy.has_operated_node(nodes)

    @staticmethod
    def cancel_pending_nodes(nodes: list[dict[str, Any]], operator: dict) -> list[dict[str, Any]]:
        operated_at = operator.get("operated_at")
        for node in nodes:
            if node.get("status") != AuditStatus.PENDING:
                continue
            node["status"] = AuditStatus.CANCELED
            node["operator"] = operator.get("username")
            node["operator_display"] = operator.get("display_name") or operator.get("username")
            if operated_at:
                node["operated_at"] = operated_at
        return nodes
