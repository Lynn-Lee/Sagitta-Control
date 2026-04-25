from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.engines.models import ResultSet
from app.models.slowlog import SlowQueryLog
from app.schemas.slowlog import SlowQueryConfigUpdate, SlowQueryConfigUpsert
from app.services.slowlog import (
    SlowLogService,
    analyze_sql,
    build_recommendations,
    normalize_sql_fingerprint,
    tag_options_by_engine,
)


def test_normalize_sql_fingerprint_groups_literals():
    fp1, text1 = normalize_sql_fingerprint("select * from orders where id = 123 and name = 'alice'")
    fp2, text2 = normalize_sql_fingerprint("SELECT * FROM orders WHERE id = 456 AND name = 'bob'")

    assert fp1 == fp2
    assert text1.lower() == "select * from orders where id = ? and name = ?"
    assert text2.lower() == "select * from orders where id = ? and name = ?"


def test_analyze_sql_marks_basic_risks():
    tags = analyze_sql(
        "select * from orders",
        rows_examined=200000,
        rows_sent=20000,
        duration_ms=12000,
    )

    assert "SELECT *" in tags
    assert "缺少 WHERE" in tags
    assert "扫描行数高" in tags
    assert "返回行数高" in tags
    assert "超长耗时" in tags


def test_analyze_sql_uses_engine_specific_tags():
    mysql_tags = analyze_sql("select * from orders where name like '%abc'", db_type="mysql")
    mssql_tags = analyze_sql("select * from orders", db_type="mssql")
    redis_tags = analyze_sql("get user:1", db_type="redis")

    assert "前导通配符" in mysql_tags
    assert "TOP 缺失" not in mysql_tags
    assert "TOP 缺失" in mssql_tags
    assert redis_tags == []


def test_tag_options_excludes_unsupported_non_sql_engines():
    options = tag_options_by_engine()

    assert "mysql" in options
    assert "pgsql" in options
    assert "oracle" in options
    assert "redis" not in options
    assert "mongo" not in options


def test_slowlog_filters_still_support_tag_filter():
    stmt = SlowLogService._filters(select(SlowQueryLog), tag="SELECT *")
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "analysis_tags" in compiled
    assert "SELECT *" in compiled


def test_build_recommendations_returns_structured_items():
    recs = build_recommendations(
        "select * from orders",
        rows_examined=200000,
        rows_sent=20,
        duration_ms=15000,
    )

    titles = {item.title for item in recs}
    assert "减少返回列" in titles
    assert "补充过滤条件" in titles
    assert "检查索引与过滤条件" in titles


def test_slow_query_config_allows_30_second_interval():
    created = SlowQueryConfigUpsert(instance_id=1, collect_interval=30)
    updated = SlowQueryConfigUpdate(collect_interval=30)

    assert created.collect_interval == 30
    assert updated.collect_interval == 30


def test_slowlog_instance_and_database_stats_are_grouped():
    rows = [
        SimpleNamespace(
            instance_id=1,
            instance_name="mysql-prod",
            db_type="mysql",
            db_name="orders",
            sql_fingerprint="fp-1",
            duration_ms=40,
            collect_error="",
            occurred_at=datetime(2026, 4, 24, 8, 0, tzinfo=UTC),
        ),
        SimpleNamespace(
            instance_id=1,
            instance_name="mysql-prod",
            db_type="mysql",
            db_name="crm",
            sql_fingerprint="fp-2",
            duration_ms=120,
            collect_error="timeout",
            occurred_at=datetime(2026, 4, 24, 9, 0, tzinfo=UTC),
        ),
        SimpleNamespace(
            instance_id=2,
            instance_name="pg-prod",
            db_type="pgsql",
            db_name="analytics",
            sql_fingerprint="fp-3",
            duration_ms=80,
            collect_error="",
            occurred_at=datetime(2026, 4, 24, 10, 0, tzinfo=UTC),
        ),
    ]

    instance_stats = SlowLogService._instance_stats(rows)
    database_stats = SlowLogService._database_stats(rows)

    assert [item.group_name for item in instance_stats] == ["mysql-prod", "pg-prod"]
    assert instance_stats[0].total == 2
    assert instance_stats[0].database_count == 2
    assert instance_stats[0].failed_count == 1
    assert {item.group_name for item in database_stats} == {"orders", "crm", "analytics"}


def test_slowlog_group_trends_follow_selected_grouping():
    rows = [
        SimpleNamespace(
            instance_id=1,
            instance_name="mysql-prod",
            db_type="mysql",
            db_name="orders",
            sql_fingerprint="fp-1",
            duration_ms=40,
            collect_error="",
            occurred_at=datetime(2026, 4, 24, 8, 0, tzinfo=UTC),
        ),
        SimpleNamespace(
            instance_id=1,
            instance_name="mysql-prod",
            db_type="mysql",
            db_name="crm",
            sql_fingerprint="fp-2",
            duration_ms=120,
            collect_error="",
            occurred_at=datetime(2026, 4, 24, 8, 30, tzinfo=UTC),
        ),
    ]

    instance_trends = SlowLogService._group_trends(rows, SlowLogService._instance_stats(rows))
    database_trends = SlowLogService._group_trends(rows, SlowLogService._database_stats(rows), by_database=True)

    assert instance_trends[0].group_name == "mysql-prod"
    assert instance_trends[0].points[0].count == 2
    assert {item.group_name for item in database_trends} == {"orders", "crm"}


def test_slowlog_fingerprint_item_includes_target_scope():
    rows = [
        SimpleNamespace(
            instance_id=1,
            instance_name="mysql-prod",
            db_type="mysql",
            db_name="orders",
            sql_text="select * from orders where id = ?",
            fingerprint_text="select * from orders where id = ?",
            sql_fingerprint="fp-1",
            duration_ms=40,
            rows_examined=10,
            rows_sent=1,
            analysis_tags=[],
            occurred_at=datetime(2026, 4, 24, 8, 0, tzinfo=UTC),
        ),
        SimpleNamespace(
            instance_id=2,
            instance_name="pg-prod",
            db_type="pgsql",
            db_name="orders",
            sql_text="select * from orders where id = ?",
            fingerprint_text="select * from orders where id = ?",
            sql_fingerprint="fp-1",
            duration_ms=80,
            rows_examined=20,
            rows_sent=1,
            analysis_tags=[],
            occurred_at=datetime(2026, 4, 24, 9, 0, tzinfo=UTC),
        ),
    ]

    item = SlowLogService._fingerprint_from_rows("fp-1", rows)

    assert item.instance_id == 2
    assert item.instance_name == "pg-prod"
    assert item.db_name == "orders"
    assert item.instance_count == 2
    assert item.database_count == 2


def test_analyze_plan_detects_mysql_full_scan_and_filesort():
    raw_plan = {
        "query_block": {
            "table": {
                "access_type": "ALL",
                "rows_examined_per_scan": 200000,
                "using_filesort": True,
            }
        }
    }

    summary, recs = SlowLogService.analyze_plan("mysql", raw_plan)

    assert summary["full_scan"] is True
    assert summary["filesort"] is True
    assert summary["rows_estimate"] == 200000
    assert any(item.title == "执行计划存在全表扫描" for item in recs)


def test_analyze_plan_detects_pg_seq_scan():
    raw_plan = [{"Plan": {"Node Type": "Seq Scan", "Plan Rows": 50000, "Total Cost": 1200}}]

    summary, recs = SlowLogService.analyze_plan("pgsql", raw_plan)

    assert summary["full_scan"] is True
    assert summary["rows_estimate"] == 50000
    assert summary["max_cost"] == 1200
    assert any(item.severity == "critical" for item in recs)


@pytest.mark.asyncio
async def test_scoped_instance_ids_superuser_is_global():
    ids = await SlowLogService.scoped_instance_ids(
        AsyncMock(),
        {"is_superuser": True, "permissions": [], "resource_groups": []},
    )

    assert ids is None


@pytest.mark.asyncio
async def test_scoped_instance_ids_without_resource_groups_is_empty():
    ids = await SlowLogService.scoped_instance_ids(
        AsyncMock(),
        {"is_superuser": False, "permissions": [], "resource_groups": []},
    )

    assert ids == []


@pytest.mark.asyncio
async def test_collect_instance_unsupported_engine_returns_message():
    count, err = await SlowLogService.collect_instance(
        AsyncMock(),
        SimpleNamespace(id=1, db_type="oracle", instance_name="ora-prod"),
        config=SimpleNamespace(is_enabled=True, collect_limit=100),
    )

    assert count == 0
    assert "暂不支持" in err


@pytest.mark.asyncio
async def test_collect_instance_passes_config_threshold_to_engine(monkeypatch):
    engine = SimpleNamespace(
        collect_slow_queries=AsyncMock(
            return_value=ResultSet(
                column_list=["source", "source_ref", "db_name", "sql_text", "duration_ms"],
                rows=[("mysql_slowlog", "digest-1", "orders", "select * from orders", 5)],
            )
        )
    )
    monkeypatch.setattr("app.services.slowlog.get_engine", lambda _instance: engine)

    exists_result = MagicMock()
    exists_result.scalar_one_or_none.return_value = None
    db = SimpleNamespace(
        execute=AsyncMock(return_value=exists_result),
        add=MagicMock(),
        commit=AsyncMock(),
    )
    instance = SimpleNamespace(id=7, db_type="mysql", instance_name="mysql-prod", db_name="orders")
    config = SimpleNamespace(
        is_enabled=True,
        collect_limit=100,
        threshold_ms=1,
        last_collect_at=None,
        last_collect_status="",
        last_collect_error="",
        last_collect_count=0,
    )

    count, err = await SlowLogService.collect_instance(db, instance, limit=100, config=config)

    assert (count, err) == (1, "")
    engine.collect_slow_queries.assert_awaited_once()
    assert engine.collect_slow_queries.await_args.kwargs["min_duration_ms"] == 1


@pytest.mark.asyncio
async def test_update_config_applies_changes_for_accessible_instance():
    cfg = SimpleNamespace(id=3, threshold_ms=1000, is_enabled=True)
    instance = SimpleNamespace(resource_groups=[SimpleNamespace(id=2)])
    result = MagicMock()
    result.first.return_value = (cfg, instance)
    db = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    updated = await SlowLogService.update_config(
        db,
        3,
        SimpleNamespace(model_dump=lambda exclude_none=True: {"threshold_ms": 2500, "is_enabled": False}),
        {"is_superuser": False, "permissions": [], "resource_groups": [2]},
    )

    assert updated.threshold_ms == 2500
    assert updated.is_enabled is False
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_configs_backfills_visible_instances_without_overwriting(monkeypatch):
    instances = [
        SimpleNamespace(
            id=1,
            instance_name="mysql-prod",
            db_type="mysql",
            is_active=True,
            resource_groups=[],
        ),
        SimpleNamespace(
            id=2,
            instance_name="pg-prod",
            db_type="pgsql",
            is_active=True,
            resource_groups=[],
        ),
    ]
    result = MagicMock()
    result.scalars.return_value.all.return_value = instances
    db = SimpleNamespace(execute=AsyncMock(return_value=result))

    configs = {
        1: SimpleNamespace(
            id=10,
            instance_id=1,
            is_enabled=True,
            threshold_ms=100,
            collect_interval=60,
            retention_days=7,
            collect_limit=50,
            last_collect_at=None,
            last_collect_status="success",
            last_collect_error="",
            last_collect_count=3,
            created_by="alice",
        ),
        2: SimpleNamespace(
            id=11,
            instance_id=2,
            is_enabled=False,
            threshold_ms=2500,
            collect_interval=300,
            retention_days=30,
            collect_limit=100,
            last_collect_at=None,
            last_collect_status="idle",
            last_collect_error="",
            last_collect_count=0,
            created_by="bob",
        ),
    }
    ensure_default = AsyncMock(side_effect=lambda _db, instance, _user: configs[instance.id])
    monkeypatch.setattr(SlowLogService, "ensure_default_config", ensure_default)

    total, items = await SlowLogService.list_configs(db, {"is_superuser": True, "permissions": []})

    assert total == 2
    assert [item.instance_name for item in items] == ["mysql-prod", "pg-prod"]
    assert [item.threshold_ms for item in items] == [100, 2500]
    assert items[0].collect_interval == 60
    assert items[0].last_collect_count == 3
    assert ensure_default.await_count == 2


@pytest.mark.asyncio
async def test_sync_platform_logs_adds_slow_query_from_query_log():
    qlog = SimpleNamespace(
        id=9,
        instance_id=2,
        instance_name="mysql-prod",
        db_type="mysql",
        db_name="orders",
        sqllog="select * from orders where id = 42",
        effect_row=15,
        cost_time_ms=1500,
        username="alice",
        client_ip="10.0.0.8",
        created_at=datetime(2026, 4, 24, 8, 0, tzinfo=UTC),
        operation_type="execute",
        error="",
        priv_check=True,
    )

    query_result = MagicMock()
    query_result.scalars.return_value.all.return_value = [qlog]
    exists_result = MagicMock()
    exists_result.scalar_one_or_none.return_value = None

    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[query_result, exists_result]),
        add=MagicMock(),
        commit=AsyncMock(),
    )

    saved = await SlowLogService.sync_platform_logs(db, threshold_ms=1000)

    assert saved == 1
    slow_log = db.add.call_args.args[0]
    assert slow_log.source == "platform"
    assert slow_log.source_ref == "query_log:9"
    assert slow_log.duration_ms == 1500
    assert slow_log.rows_sent == 15
    assert "SELECT *" in slow_log.analysis_tags
    db.commit.assert_awaited_once()
