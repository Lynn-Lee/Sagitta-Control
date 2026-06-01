"""ClickHouse 引擎单元测试。"""

from __future__ import annotations

import pytest

from app.engines.clickhouse import ClickHouseEngine
from app.engines.models import ResultSet


class MockInstance:
    db_type = "clickhouse"
    host = "localhost"
    port = 8123
    user = ""
    password = ""
    db_name = "default"
    show_db_name_regex = ""


class FakeQueryResult:
    def __init__(self, rows, columns=None):
        self.result_rows = rows
        self.column_names = columns or []


class FakeClient:
    def __init__(self):
        self.queries: list[tuple[str, dict | None]] = []

    def command(self, sql):
        if "version()" in sql:
            return "24.8.1"
        if "uptime()" in sql:
            return 3600
        return None

    def query(self, sql, parameters=None):
        self.queries.append((sql, parameters))
        if "FROM system.tables" in sql:
            return FakeQueryResult([("id", "id, created_at")])
        if "FROM system.data_skipping_indices" in sql:
            return FakeQueryResult([("idx_status", "status", "set(100)")])
        if "FROM system.metrics" in sql:
            return FakeQueryResult(
                [
                    ("HTTPConnection", 2),
                    ("TCPConnection", 3),
                    ("Query", 4),
                    ("DelayedInserts", 1),
                ]
            )
        if "FROM system.events" in sql:
            return FakeQueryResult(
                [
                    ("Query", 1200),
                    ("SelectQuery", 1000),
                    ("InsertQuery", 200),
                    ("FailedQuery", 3),
                ]
            )
        if "FROM system.asynchronous_metrics" in sql:
            return FakeQueryResult(
                [
                    ("MemoryTracking", 1024),
                    ("OSMemoryTotal", 4096),
                    ("OSMemoryAvailable", 2048),
                ]
            )
        if "FROM system.disks" in sql:
            return FakeQueryResult([("default", "/var/lib/clickhouse/", 1024, 4096, 0)])
        if "FROM system.settings" in sql:
            return FakeQueryResult([("max_connections", "100")])
        return FakeQueryResult([])


def _engine(client=None) -> ClickHouseEngine:
    engine = ClickHouseEngine(MockInstance())
    if client is not None:
        engine._client = lambda db_name=None: client
    return engine


@pytest.mark.asyncio
async def test_clickhouse_exposes_primary_sorting_and_skip_indexes():
    client = FakeClient()
    engine = _engine(client)

    constraints = await engine.get_table_constraints("analytics", "events")
    indexes = await engine.get_table_indexes("analytics", "events")

    assert constraints.rows == [
        {
            "constraint_name": "events_primary_key",
            "constraint_type": "PRIMARY KEY",
            "column_names": "id",
            "referenced_table_name": "",
            "referenced_column_names": "",
            "check_clause": "",
        },
        {
            "constraint_name": "events_sorting_key",
            "constraint_type": "ORDER BY",
            "column_names": "id, created_at",
            "referenced_table_name": "",
            "referenced_column_names": "",
            "check_clause": "",
        },
    ]
    assert indexes.rows[0]["index_type"] == "PRIMARY KEY"
    assert indexes.rows[1]["index_type"] == "ORDER BY"
    assert indexes.rows[2]["index_name"] == "idx_status"
    assert indexes.rows[2]["index_type"] == "set(100) DATA SKIPPING INDEX"


@pytest.mark.asyncio
async def test_clickhouse_sql_activity_converts_elapsed_seconds(monkeypatch):
    engine = _engine()

    async def fake_processlist(**kwargs):
        return ResultSet(
            column_list=["query_id", "user", "elapsed_sec", "query"],
            rows=[("q1", "default", 2.5, "select * from events")],
        )

    monkeypatch.setattr(engine, "processlist", fake_processlist)

    rs = await engine.collect_sql_activity(limit=10, min_duration_ms=1000)

    assert rs.rows[0]["source"] == "clickhouse_activity"
    assert rs.rows[0]["source_ref"] == "clickhouse:q1"
    assert rs.rows[0]["duration_ms"] == 2500


@pytest.mark.asyncio
async def test_clickhouse_collect_metrics_maps_engine_specific_groups():
    engine = _engine(FakeClient())

    metrics = await engine.collect_metrics()

    assert metrics["health"]["up"] == 1
    assert metrics["version"]["value"] == "24.8.1"
    assert metrics["connections"]["current"] == 5
    assert metrics["connections"]["active_sessions"] == 4
    assert metrics["memory"]["memory_usage"] == 0.25
    assert metrics["stats"]["error_count"] == 3
    assert metrics["counters"]["queries"] == 1200
    assert metrics["disks"][0]["used_pct"] == 75.0
