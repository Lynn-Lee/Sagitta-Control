from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.slowlog import (
    SlowLogService,
    analyze_sql,
    build_recommendations,
    normalize_sql_fingerprint,
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
