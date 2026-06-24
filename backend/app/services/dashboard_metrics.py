"""Dashboard 指标序列组装工具。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def build_date_keys(period_start: datetime, days: int) -> list[str]:
    return [(period_start.date() + timedelta(days=offset)).isoformat() for offset in range(days)]


def build_query_trend_payload(
    *,
    period_start: datetime,
    days: int,
    query_map: dict[str, dict[str, int]],
    query_failure_map: dict[str, int],
    masked_map: dict[str, int],
    approved_map: dict[str, int],
    rejected_map: dict[str, int],
    revoked_map: dict[str, int],
    pending_stock_count: list[int],
) -> dict[str, Any]:
    dates = build_date_keys(period_start, days)
    return {
        "dates": dates,
        "query_count": [query_map.get(day, {}).get("query_count", 0) for day in dates],
        "query_user_count": [query_map.get(day, {}).get("query_user_count", 0) for day in dates],
        "failure_count": [
            query_failure_map.get(day, 0) + rejected_map.get(day, 0) for day in dates
        ],
        "masked_count": [masked_map.get(day, 0) for day in dates],
        "approved_count": [approved_map.get(day, 0) for day in dates],
        "rejected_count": [rejected_map.get(day, 0) for day in dates],
        "revoked_count": [revoked_map.get(day, 0) for day in dates],
        "pending_stock_count": pending_stock_count,
    }
