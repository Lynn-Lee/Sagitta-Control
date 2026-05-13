from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AppException
from app.models.monitor import MonitorMetricSnapshot
from app.schemas.monitor import UnifiedCollectConfigUpsert
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
    normalized = MonitorService._normalize_metric_payload(
        {"health": {"up": 0}, "error": "permission denied"}
    )

    assert normalized["status"] == "failed"
    assert normalized["is_up"] is False
    assert normalized["missing_groups"] == {"health": "collect_failed"}
    assert normalized["error"] == "permission denied"


def test_normalize_metric_payload_preserves_partial_missing_groups():
    normalized = MonitorService._normalize_metric_payload(
        {
            "health": {"up": 1},
            "connections": {"current": Decimal("8"), "max_connections": Decimal("100")},
            "stats": {"qps": Decimal("12.5")},
            "missing_groups": {"stats": "missing v$sysmetric permission"},
        }
    )

    assert normalized["status"] == "success"
    assert normalized["missing_groups"] == {"stats": "missing v$sysmetric permission"}
    assert normalized["connection_usage"] == 0.08
    assert normalized["qps"] == 12.5
    assert normalized["extra_metrics"]["stats"]["qps"] == 12.5


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


def test_evaluate_health_scores_oracle_tablespace_and_fra_risk():
    health = MonitorService.evaluate_health(
        {
            "is_up": True,
            "status": "success",
            "connection_usage": 0.92,
            "lock_waits": 3,
            "extra_metrics": {
                "tablespaces": [{"tablespace_name": "USERS", "used_pct": 91}],
                "fra": {"used_pct": 86},
            },
        },
        "success",
    )

    assert health["risk_level"] in {"warning", "critical"}
    assert "连接使用率 92%" in health["risk_reasons"]
    assert "USERS 表空间 91%" in health["risk_reasons"]
    assert "FRA 使用率 86%" in health["risk_reasons"]


def test_apply_delta_rates_prefers_interval_counters():
    previous = MonitorMetricSnapshot(
        instance_id=1,
        collected_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        extra_metrics={"counters": {"queries": 1000, "transactions": 200}},
    )
    normalized = {"qps": 1, "tps": 1}

    MonitorService._apply_delta_rates(
        normalized,
        {"counters": {"queries": 1600, "transactions": 260}},
        previous,
        datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
    )

    assert normalized["qps"] == 10
    assert normalized["tps"] == 1


def test_mysql_trend_slow_queries_uses_delta_from_legacy_cumulative_counter():
    previous = SimpleNamespace(extra_metrics={"stats": {"slow_queries": 121800}})
    row = SimpleNamespace(slow_queries=121866, extra_metrics={"stats": {"slow_queries": 121866}})

    value, next_total = MonitorService._mysql_trend_slow_queries(
        row,
        MonitorService._mysql_slow_query_total(previous),
    )

    assert value == 66
    assert next_total == 121866


def test_mysql_trend_slow_queries_uses_total_counter_from_new_snapshots():
    row = SimpleNamespace(
        slow_queries=2,
        extra_metrics={"stats": {"slow_queries": 2, "slow_queries_total": 122006, "lock_waits": 1}},
    )

    value, next_total = MonitorService._mysql_trend_slow_queries(row, 122000)

    assert value == 6
    assert next_total == 122006


def test_mysql_trend_slow_queries_falls_back_to_current_snapshot_value():
    row = SimpleNamespace(
        slow_queries=3,
        extra_metrics={"stats": {"slow_queries": 3, "lock_waits": 1}},
    )

    value, next_total = MonitorService._mysql_trend_slow_queries(row, None)

    assert value == 3
    assert next_total is None


@pytest.mark.asyncio
async def test_get_top_sql_uses_activity_collector_for_starrocks(monkeypatch):
    instance = SimpleNamespace(id=28, db_type="starrocks")
    engine = SimpleNamespace(
        collect_sql_activity=AsyncMock(
            return_value=SimpleNamespace(
                is_success=True,
                error="",
                column_list=[],
                rows=[
                    {
                        "source_ref": "starrocks:10",
                        "db_name": "warehouse",
                        "sql_text": "select * from orders",
                        "duration_ms": 3000,
                    }
                ],
            )
        ),
        collect_slow_queries=AsyncMock(),
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: instance))
    )
    monkeypatch.setattr(MonitorService, "check_privilege", AsyncMock(return_value=True))
    monkeypatch.setattr(MonitorService, "get_latest_snapshot", AsyncMock(return_value=None))
    monkeypatch.setattr("app.engines.registry.get_engine", lambda _instance: engine)

    result = await MonitorService.get_top_sql(db, 28, {"is_superuser": True}, limit=5)

    engine.collect_sql_activity.assert_awaited_once_with(limit=5)
    engine.collect_slow_queries.assert_not_awaited()
    assert result["error"] == ""
    assert result["items"][0]["source_ref"] == "starrocks:10"


@pytest.mark.asyncio
async def test_unified_collect_config_list_uses_accessible_instances(monkeypatch):
    instances = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    monkeypatch.setattr(MonitorService, "_accessible_instances", AsyncMock(return_value=instances))
    monkeypatch.setattr(
        MonitorService,
        "_unified_collect_config_item",
        AsyncMock(side_effect=[
            {"instance_id": 1, "native": {}, "session": {}, "sql": {}},
            {"instance_id": 2, "native": {}, "session": {}, "sql": {}},
        ]),
    )
    db = SimpleNamespace(commit=AsyncMock())

    result = await MonitorService.list_unified_collect_configs(db, {"is_superuser": True})

    assert result["total"] == 2
    assert [item["instance_id"] for item in result["items"]] == [1, 2]
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_unified_collect_config_rejects_resource_group_outside_instance():
    instance = SimpleNamespace(id=9, is_active=True, resource_groups=[SimpleNamespace(id=2)])
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = instance
    db = SimpleNamespace(execute=AsyncMock(return_value=execute_result))

    with pytest.raises(AppException):
        await MonitorService.upsert_unified_collect_config(
            db,
            9,
            UnifiedCollectConfigUpsert(),
            {"is_superuser": False, "permissions": [], "resource_groups": [1]},
        )


@pytest.mark.asyncio
async def test_unified_collect_config_updates_all_three_collectors(monkeypatch):
    instance = SimpleNamespace(id=3, instance_name="mysql-prod", db_type="mysql", resource_groups=[])
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = instance
    db = SimpleNamespace(execute=AsyncMock(return_value=execute_result))
    native_upsert = AsyncMock()
    session_upsert = AsyncMock()
    slow_upsert = AsyncMock()
    monkeypatch.setattr(MonitorService, "upsert_native_config", native_upsert)
    monkeypatch.setattr(
        "app.services.session_diagnostic.SessionDiagnosticService.upsert_config",
        session_upsert,
    )
    monkeypatch.setattr("app.services.slowlog.SlowLogService.upsert_config", slow_upsert)
    monkeypatch.setattr(
        MonitorService,
        "_unified_collect_config_item",
        AsyncMock(return_value={"instance_id": 3, "native": {}, "session": {}, "sql": {}}),
    )

    result = await MonitorService.upsert_unified_collect_config(
        db,
        3,
        UnifiedCollectConfigUpsert(),
        {"is_superuser": True, "username": "admin", "permissions": []},
    )

    assert result["instance_id"] == 3
    native_upsert.assert_awaited_once()
    session_upsert.assert_awaited_once()
    slow_upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_unified_collect_config_applies_visible_instances(monkeypatch):
    instances = [
        SimpleNamespace(id=1, instance_name="mysql-prod"),
        SimpleNamespace(id=2, instance_name="pg-prod"),
    ]
    monkeypatch.setattr(MonitorService, "_accessible_instances", AsyncMock(return_value=instances))
    monkeypatch.setattr(MonitorService, "upsert_unified_collect_config", AsyncMock(return_value={}))

    result = await MonitorService.bulk_upsert_unified_collect_configs(
        SimpleNamespace(),
        UnifiedCollectConfigUpsert(),
        {"is_superuser": True},
    )

    assert result["total"] == 2
    assert result["success"] == 2
    assert result["failed"] == []
