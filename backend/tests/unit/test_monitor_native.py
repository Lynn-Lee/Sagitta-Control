from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AppException
from app.models.monitor import MonitorCollectConfig, MonitorMetricSnapshot
from app.schemas.monitor import UnifiedCollectConfigUpsert
from app.services.monitor import MonitorService
from app.services.monitor_alerts import MonitorAlertService


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


def test_extract_metric_groups_merges_nested_and_top_level_engine_groups():
    groups = MonitorService._extract_metric_groups(
        {
            "health": {"up": 1},
            "version": {"value": "8.0"},
            "metric_groups": {"token_usage": [{"instance": "tidb-1"}]},
            "stats": {"qps": Decimal("12.5")},
        }
    )

    assert groups == {
        "token_usage": [{"instance": "tidb-1"}],
        "stats": {"qps": 12.5},
    }


def test_snapshot_to_dict_exposes_metric_groups():
    snapshot = MonitorMetricSnapshot(
        instance_id=1,
        collected_at=datetime(2026, 1, 1, tzinfo=UTC),
        status="success",
        is_up=True,
        extra_metrics={"health": {"up": 1}, "memory": {"used_memory": Decimal("1024")}},
    )

    data = MonitorService._snapshot_to_dict(snapshot)

    assert data["metric_groups"] == {"memory": {"used_memory": 1024}}
    assert data["extra_metrics"]["memory"]["used_memory"] == Decimal("1024")


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


def test_evaluate_health_scores_redis_and_clickhouse_engine_risks():
    redis_health = MonitorService.evaluate_health(
        {
            "is_up": True,
            "status": "success",
            "extra_metrics": {
                "memory": {"memory_usage": 0.91},
                "stats": {"keyspace_hit_rate": 0.5, "evicted_keys": 2},
            },
        },
        "success",
    )
    clickhouse_health = MonitorService.evaluate_health(
        {
            "is_up": True,
            "status": "success",
            "extra_metrics": {
                "stats": {"delayed_inserts": 1, "rejected_inserts": 1},
                "disks": [{"name": "default", "used_pct": 92}],
            },
        },
        "success",
    )

    assert "内存使用率 91%" in redis_health["risk_reasons"]
    assert "缓存命中率 50%" in redis_health["risk_reasons"]
    assert "Redis 已发生 2 次 Key 淘汰" in redis_health["risk_reasons"]
    assert "ClickHouse 延迟写入 1" in clickhouse_health["risk_reasons"]
    assert "ClickHouse 拒绝写入 1" in clickhouse_health["risk_reasons"]
    assert "default 磁盘 92%" in clickhouse_health["risk_reasons"]


@pytest.mark.asyncio
async def test_sync_alert_events_notifies_when_active_alert_recovers(monkeypatch):
    event = SimpleNamespace(
        id=12,
        instance_id=8,
        rule_key="connection_usage",
        severity="warning",
        status="firing",
        title="prod-mysql connection_usage 告警",
        message="connection_usage 当前值 0.9，触发条件 >= 0.8",
        metric_value=0.9,
        threshold=0.8,
        snapshot_id=99,
        first_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
        last_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
        resolved_at=None,
        acknowledged_at=None,
        acknowledged_by="",
        silenced_until=None,
        closed_at=None,
        closed_by="",
        close_reason="",
        extra={},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [event]))
        )
    )
    instance = SimpleNamespace(id=8, instance_name="prod-mysql", db_type="mysql")
    cfg = MonitorCollectConfig(
        instance_id=8,
        alert_rules_override={"connection_usage": {"threshold": 0.8, "recover_notify": True}},
    )
    snapshot = MonitorMetricSnapshot(
        id=100,
        instance_id=8,
        collected_at=datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
        connection_usage=0.2,
        extra_metrics={},
    )
    enqueue = MagicMock()
    monkeypatch.setattr("app.services.monitor_alerts.NotifyService.enqueue_event", enqueue)

    await MonitorAlertService.sync_alert_events_for_snapshot(db, instance, cfg, snapshot)

    assert event.status == "resolved"
    assert event.resolved_at == snapshot.collected_at
    enqueue.assert_called_once()
    assert enqueue.call_args.args[0]["event_type"] == "alert_resolved"


@pytest.mark.asyncio
async def test_change_alert_event_supports_manual_resolve(monkeypatch):
    event = SimpleNamespace(
        id=12,
        instance_id=8,
        rule_key="connection_usage",
        severity="warning",
        status="acknowledged",
        title="prod-mysql connection_usage 告警",
        message="connection_usage 当前值 0.9，触发条件 >= 0.8",
        metric_value=0.9,
        threshold=0.8,
        snapshot_id=99,
        first_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
        last_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
        resolved_at=None,
        acknowledged_at=datetime(2026, 1, 1, tzinfo=UTC),
        acknowledged_by="值班同学",
        silenced_until=None,
        closed_at=None,
        closed_by="",
        close_reason="",
        extra={},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    instance = SimpleNamespace(id=8, instance_name="prod-mysql", db_type="mysql")
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(first=lambda: (event, instance))),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    enqueue = MagicMock()
    monkeypatch.setattr("app.services.monitor_alerts.NotifyService.enqueue_event", enqueue)

    result = await MonitorAlertService.change_alert_event(
        db,
        12,
        "resolve",
        {"is_superuser": True, "display_name": "运维负责人"},
    )

    assert result["status"] == "resolved"
    assert event.resolved_at is not None
    db.commit.assert_awaited_once()
    enqueue.assert_called_once()
    assert enqueue.call_args.args[0]["event_type"] == "alert_resolved"


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
async def test_get_top_sql_passes_oracle_window_to_activity_collector(monkeypatch):
    instance = SimpleNamespace(id=32, db_type="oracle")
    engine = SimpleNamespace(
        collect_sql_activity=AsyncMock(
            return_value=SimpleNamespace(
                is_success=True,
                error="",
                warning="AWR unavailable, used cursor cache",
                column_list=[],
                rows=[
                    {
                        "source": "oracle_cursor_cache",
                        "source_ref": "oracle:cursor_cache:1:abc:123",
                        "sql_text": "select * from orders",
                    }
                ],
            )
        )
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: instance))
    )
    date_start = datetime(2026, 5, 14, 10, 0, tzinfo=UTC)
    date_end = datetime(2026, 5, 14, 10, 30, tzinfo=UTC)
    monkeypatch.setattr(MonitorService, "check_privilege", AsyncMock(return_value=True))
    monkeypatch.setattr(
        MonitorService,
        "get_latest_snapshot",
        AsyncMock(return_value={"extra_metrics": {"top_sql": [{"source": "cached"}]}}),
    )
    monkeypatch.setattr("app.engines.registry.get_engine", lambda _instance: engine)

    result = await MonitorService.get_top_sql(
        db,
        32,
        {"is_superuser": True},
        limit=5,
        window_minutes=15,
        date_start=date_start,
        date_end=date_end,
    )

    engine.collect_sql_activity.assert_awaited_once_with(
        limit=5,
        min_duration_ms=0,
        window_minutes=30,
        start_time=date_start,
        end_time=date_end,
    )
    assert result["error"] == "AWR unavailable, used cursor cache"
    assert result["items"][0]["source"] == "oracle_cursor_cache"


@pytest.mark.asyncio
async def test_get_top_sql_uses_tidb_top_sql_collector(monkeypatch):
    instance = SimpleNamespace(id=29, db_type="tidb")
    engine = SimpleNamespace(
        collect_top_sql=AsyncMock(
            return_value=SimpleNamespace(
                is_success=True,
                error="",
                column_list=[],
                rows=[
                    {
                        "source_ref": "tidb:top_sql:d1",
                        "db_name": "test",
                        "sql_text": "select * from orders",
                        "executions": 2,
                        "elapsed_time_ms": 800,
                        "avg_elapsed_ms": 400,
                    }
                ],
            )
        ),
        collect_sql_activity=AsyncMock(),
        collect_slow_queries=AsyncMock(),
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: instance))
    )
    monkeypatch.setattr(MonitorService, "check_privilege", AsyncMock(return_value=True))
    monkeypatch.setattr(MonitorService, "get_latest_snapshot", AsyncMock(return_value=None))
    monkeypatch.setattr("app.engines.registry.get_engine", lambda _instance: engine)

    result = await MonitorService.get_top_sql(db, 29, {"is_superuser": True}, limit=5)

    engine.collect_top_sql.assert_awaited_once_with(limit=5, window_minutes=30)
    engine.collect_sql_activity.assert_not_awaited()
    engine.collect_slow_queries.assert_not_awaited()
    assert result["error"] == ""
    assert result["window_minutes"] == 30
    assert result["items"][0]["avg_elapsed_ms"] == 400


@pytest.mark.asyncio
async def test_get_top_sql_passes_tidb_window_minutes(monkeypatch):
    instance = SimpleNamespace(id=30, db_type="tidb")
    engine = SimpleNamespace(
        collect_top_sql=AsyncMock(
            return_value=SimpleNamespace(
                is_success=True,
                error="",
                column_list=[],
                rows=[{"source_ref": "tidb:top_sql:d2", "sql_text": "select 1"}],
            )
        ),
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: instance))
    )
    monkeypatch.setattr(MonitorService, "check_privilege", AsyncMock(return_value=True))
    monkeypatch.setattr(
        MonitorService,
        "get_latest_snapshot",
        AsyncMock(return_value={"extra_metrics": {"top_sql": [{"source_ref": "cached"}]}}),
    )
    monkeypatch.setattr("app.engines.registry.get_engine", lambda _instance: engine)

    result = await MonitorService.get_top_sql(
        db,
        30,
        {"is_superuser": True},
        limit=5,
        window_minutes=60,
    )

    engine.collect_top_sql.assert_awaited_once_with(limit=5, window_minutes=60)
    assert result["window_minutes"] == 60
    assert result["items"][0]["source_ref"] == "tidb:top_sql:d2"


@pytest.mark.asyncio
async def test_get_top_sql_passes_tidb_custom_time_range(monkeypatch):
    instance = SimpleNamespace(id=31, db_type="tidb")
    engine = SimpleNamespace(
        collect_top_sql=AsyncMock(
            return_value=SimpleNamespace(
                is_success=True,
                error="",
                column_list=[],
                rows=[{"source_ref": "tidb:top_sql:d3", "sql_text": "select 2"}],
            )
        ),
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: instance))
    )
    date_start = datetime(2026, 5, 14, 10, 0, tzinfo=UTC)
    date_end = datetime(2026, 5, 14, 10, 45, tzinfo=UTC)
    monkeypatch.setattr(MonitorService, "check_privilege", AsyncMock(return_value=True))
    monkeypatch.setattr(MonitorService, "get_latest_snapshot", AsyncMock(return_value=None))
    monkeypatch.setattr("app.engines.registry.get_engine", lambda _instance: engine)

    result = await MonitorService.get_top_sql(
        db,
        31,
        {"is_superuser": True},
        limit=5,
        window_minutes=30,
        date_start=date_start,
        date_end=date_end,
    )

    engine.collect_top_sql.assert_awaited_once_with(
        limit=5,
        window_minutes=45,
        start_time=date_start,
        end_time=date_end,
    )
    assert result["window_minutes"] == 45
    assert result["date_start"] == "2026-05-14T10:00:00+00:00"
    assert result["date_end"] == "2026-05-14T10:45:00+00:00"


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
