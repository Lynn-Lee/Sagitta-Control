from datetime import UTC, datetime

from app.services.monitor import MonitorService


def test_normalize_metric_payload_keeps_missing_values_none():
    payload = {
        "health": {"up": 1},
        "connections": {"current": 8, "max_connections": 100, "active_sessions": 3},
        "stats": {"qps": 12.5, "slow_queries": 2, "lock_waits": 1},
        "version": {"value": "8.0.36"},
    }

    normalized = MonitorService._normalize_metric_payload(payload)

    assert normalized["is_up"] is True
    assert normalized["version"] == "8.0.36"
    assert normalized["current_connections"] == 8
    assert normalized["active_sessions"] == 3
    assert normalized["connection_usage"] == 0.08
    assert normalized["qps"] == 12.5
    assert normalized["tps"] is None
    assert normalized["slow_queries"] == 2
    assert normalized["lock_waits"] == 1


def test_normalize_metric_payload_records_collect_failure():
    normalized = MonitorService._normalize_metric_payload({"health": {"up": 0}, "error": "permission denied"})

    assert normalized["status"] == "failed"
    assert normalized["is_up"] is False
    assert normalized["missing_groups"] == {"health": "collect_failed"}
    assert normalized["error"] == "permission denied"


def test_normalize_table_capacity_maps_common_engine_fields():
    row = MonitorService._normalize_table_capacity(
        1,
        "app",
        {
            "TABLE_NAME": "orders",
            "TABLE_ROWS": "10",
            "DATA_LENGTH": "2048",
            "INDEX_LENGTH": "1024",
        },
        datetime.now(UTC),
    )

    assert row.table_name == "orders"
    assert row.row_count == 10
    assert row.data_size_bytes == 2048
    assert row.index_size_bytes == 1024
    assert row.total_size_bytes == 3072
