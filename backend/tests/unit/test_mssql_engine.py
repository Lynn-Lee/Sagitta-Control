"""MSSQL 引擎单元测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.engines.models import ResultSet
from app.engines.mssql import MssqlEngine


class MockInstance:
    db_type = "mssql"
    host = "localhost"
    port = 1433
    user = ""
    password = ""
    db_name = "master"
    show_db_name_regex = ""


def _engine() -> MssqlEngine:
    return MssqlEngine(MockInstance())


def test_mssql_filter_sql_injects_top_without_wrapping_ordered_select():
    engine = _engine()

    filtered = engine.filter_sql("SELECT id FROM orders ORDER BY id DESC", 20)

    assert filtered == "SELECT TOP (20) id FROM orders ORDER BY id DESC"


def test_mssql_filter_sql_preserves_existing_top_and_distinct():
    engine = _engine()

    assert engine.filter_sql("SELECT TOP (5) id FROM orders", 20) == "SELECT TOP (5) id FROM orders"
    assert engine.filter_sql("SELECT DISTINCT id FROM orders", 20) == (
        "SELECT DISTINCT TOP (20) id FROM orders"
    )


@pytest.mark.asyncio
async def test_mssql_processlist_uses_dmvs_and_normalizes_rows(monkeypatch):
    engine = _engine()
    captured: dict = {}

    def fake_run_query_sync(sql, params=None, db_name=None):
        captured["sql"] = sql
        captured["params"] = params
        captured["db_name"] = db_name
        return ResultSet(
            column_list=["session_id", "username", "duration_ms", "sql_text"],
            rows=[(52, "sa", 1500, "select 1")],
        )

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)
    monkeypatch.setattr("app.engines.mssql.asyncio.to_thread", fake_to_thread)

    rs = await engine.processlist(command_type="SELECT")

    assert "sys.dm_exec_sessions" in captured["sql"]
    assert "sys.dm_exec_requests" in captured["sql"]
    assert captured["params"] == ("SELECT",)
    assert captured["db_name"] == "master"
    assert rs.rows[0]["session_id"] == 52
    assert rs.rows[0]["duration_ms"] == 1500


@pytest.mark.asyncio
async def test_mssql_kill_connection_uses_kill_statement(monkeypatch):
    engine = _engine()
    captured: dict = {}

    def fake_run_query_sync(sql, params=None, db_name=None):
        captured["sql"] = sql
        captured["params"] = params
        captured["db_name"] = db_name
        return ResultSet(affected_rows=0)

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)
    monkeypatch.setattr("app.engines.mssql.asyncio.to_thread", fake_to_thread)

    rs = await engine.kill_connection(52)

    assert rs.is_success
    assert captured == {"sql": "KILL 52", "params": None, "db_name": "master"}


@pytest.mark.asyncio
async def test_mssql_collect_sql_activity_uses_dmvs_and_normalizes_rows(monkeypatch):
    engine = _engine()
    captured: dict = {}

    def fake_run_query_sync(sql, params=None, db_name=None):
        captured["sql"] = sql
        captured["params"] = params
        captured["db_name"] = db_name
        return ResultSet(
            column_list=[
                "source",
                "source_ref",
                "db_name",
                "sql_text",
                "duration_ms",
                "username",
                "client_host",
                "command",
                "state",
            ],
            rows=[
                (
                    "mssql_activity",
                    "mssql:52:0x01",
                    "demo",
                    "SELECT * FROM orders",
                    1200,
                    "sa",
                    "app-host",
                    "SELECT",
                    "running",
                )
            ],
        )

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)
    monkeypatch.setattr("app.engines.mssql.asyncio.to_thread", fake_to_thread)

    rs = await engine.collect_sql_activity(limit=25, min_duration_ms=500)

    assert "sys.dm_exec_requests" in captured["sql"]
    assert "sys.dm_exec_sessions" in captured["sql"]
    assert captured["params"] == (25, 500)
    assert captured["db_name"] == "master"
    assert rs.rows[0]["source"] == "mssql_activity"
    assert rs.rows[0]["duration_ms"] == 1200


@pytest.mark.asyncio
async def test_mssql_execute_workflow_reads_split_content(monkeypatch):
    engine = _engine()
    captured: dict = {}

    async def fake_execute(db_name, sql, **kwargs):
        captured["db_name"] = db_name
        captured["sql"] = sql
        captured["kwargs"] = kwargs
        return ResultSet()

    monkeypatch.setattr(engine, "execute", fake_execute)
    workflow = SimpleNamespace(db_name="demo", content=SimpleNamespace(sql_content="UPDATE t SET c = 1"))

    await engine.execute_workflow(workflow)

    assert captured == {"db_name": "demo", "sql": "UPDATE t SET c = 1", "kwargs": {}}


@pytest.mark.asyncio
async def test_mssql_collect_metrics_returns_version_database_and_session_groups(monkeypatch):
    engine = _engine()
    calls: list[str] = []

    async def fake_test_connection():
        return ResultSet(rows=[(1,)], column_list=["result"], affected_rows=1)

    def fake_run_query_sync(sql, params=None, db_name=None):
        calls.append(sql)
        if "SERVERPROPERTY" in sql:
            return ResultSet(column_list=["version"], rows=[("16.0.1000.6",)])
        if "FROM sys.databases" in sql:
            return ResultSet(
                column_list=["database_count", "online_database_count"],
                rows=[(6, 5)],
            )
        if "FROM sys.dm_exec_sessions" in sql:
            return ResultSet(
                column_list=["session_count", "user_session_count"],
                rows=[(14, 9)],
            )
        return ResultSet(error="unexpected sql")

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(engine, "test_connection", fake_test_connection)
    monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)
    monkeypatch.setattr("app.engines.mssql.asyncio.to_thread", fake_to_thread)

    metrics = await engine.collect_metrics()

    assert metrics["health"]["up"] == 1
    assert metrics["version"]["value"] == "16.0.1000.6"
    assert metrics["databases"]["total"] == 6
    assert metrics["sessions"]["user"] == 9
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_mssql_collect_metrics_reports_health_failure(monkeypatch):
    engine = _engine()

    async def fake_test_connection():
        return ResultSet(error="login failed")

    monkeypatch.setattr(engine, "test_connection", fake_test_connection)

    metrics = await engine.collect_metrics()

    assert metrics == {"health": {"up": 0, "error": "login failed"}}
