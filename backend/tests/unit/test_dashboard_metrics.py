from __future__ import annotations

from datetime import UTC, datetime

from app.services.dashboard_metrics import build_query_trend_payload


def test_build_query_trend_payload_fills_missing_days_and_combines_failures():
    payload = build_query_trend_payload(
        period_start=datetime(2026, 6, 22, tzinfo=UTC),
        days=3,
        query_map={
            "2026-06-22": {"query_count": 4, "query_user_count": 2},
            "2026-06-24": {"query_count": 8, "query_user_count": 3},
        },
        query_failure_map={"2026-06-22": 1},
        masked_map={"2026-06-24": 2},
        approved_map={"2026-06-23": 5},
        rejected_map={"2026-06-22": 2, "2026-06-24": 1},
        revoked_map={"2026-06-23": 1},
        pending_stock_count=[7, 6, 4],
    )

    assert payload == {
        "dates": ["2026-06-22", "2026-06-23", "2026-06-24"],
        "query_count": [4, 0, 8],
        "query_user_count": [2, 0, 3],
        "failure_count": [3, 0, 1],
        "masked_count": [0, 0, 2],
        "approved_count": [0, 5, 0],
        "rejected_count": [2, 0, 1],
        "revoked_count": [0, 1, 0],
        "pending_stock_count": [7, 6, 4],
    }
