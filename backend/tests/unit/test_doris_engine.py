"""Doris 引擎单元测试。"""

import pytest

from app.engines.doris import DorisEngine
from app.engines.models import ResultSet


class MockInstance:
    db_type = "doris"
    host = "localhost"
    port = 9030
    user = ""
    password = ""
    db_name = "demo"
    show_db_name_regex = ""


class FakeDorisEngine(DorisEngine):
    def __init__(self, responses: dict[str, ResultSet] | None = None):
        super().__init__(MockInstance())
        self.responses = responses or {}
        self.seen: list[tuple[str, str, dict | None]] = []

    async def query(
        self,
        db_name: str,
        sql: str,
        limit_num: int = 0,
        parameters: dict | None = None,
        **kwargs,
    ) -> ResultSet:
        self.seen.append((db_name, sql, parameters))
        key = sql.lower()
        for pattern, response in self.responses.items():
            if pattern in key:
                return response
        return ResultSet(rows=[{"ok": 1}], column_list=["ok"], affected_rows=1)


def test_doris_query_check_blocks_write_operation():
    engine = DorisEngine(MockInstance())

    result = engine.query_check("demo", "DELETE FROM orders")

    assert "不允许" in result["msg"]


def test_doris_adds_limit_to_select_only():
    engine = DorisEngine(MockInstance())

    assert engine.filter_sql("SELECT id FROM orders", 10).endswith("LIMIT 10")
    assert engine.filter_sql("SHOW TABLES", 10) == "SHOW TABLES"


@pytest.mark.asyncio
async def test_doris_connection_reads_version():
    engine = FakeDorisEngine(
        {
            "select 1": ResultSet(rows=[{"ok": 1}], column_list=["ok"]),
            "current_version": ResultSet(rows=[{"version": "2.1.7"}], column_list=["version"]),
        }
    )

    rs = await engine.test_connection()

    assert rs.is_success
    assert rs.rows == [("ok", "2.1.7")]


@pytest.mark.asyncio
async def test_doris_uses_mysql_information_schema_for_columns():
    engine = FakeDorisEngine()

    await engine.get_all_columns_by_tb("demo", "orders")

    db_name, sql, params = engine.seen[-1]
    assert db_name == "demo"
    assert "information_schema.COLUMNS" in sql
    assert params == {"db": "demo", "tb": "orders"}


@pytest.mark.asyncio
async def test_doris_sql_activity_converts_processlist_seconds_to_milliseconds(monkeypatch):
    engine = DorisEngine(MockInstance())

    async def fake_processlist(command_type="Query", **kwargs):
        return ResultSet(
            rows=[
                {
                    "ID": 10,
                    "DB": "demo",
                    "INFO": "select * from orders",
                    "TIME": 2.5,
                    "USER": "app",
                    "HOST": "10.0.0.1",
                    "COMMAND": "Query",
                    "STATE": "running",
                }
            ]
        )

    monkeypatch.setattr(engine, "processlist", fake_processlist)

    rs = await engine.collect_sql_activity(limit=10, min_duration_ms=2000)

    assert rs.rows[0]["duration_ms"] == 2500
    assert rs.rows[0]["source_ref"] == "doris:10"


@pytest.mark.asyncio
async def test_doris_sql_activity_prefers_existing_duration_ms(monkeypatch):
    engine = DorisEngine(MockInstance())

    async def fake_processlist(command_type="Query", **kwargs):
        return ResultSet(rows=[{"session_id": 11, "sql_text": "select 1", "duration_ms": 1200}])

    monkeypatch.setattr(engine, "processlist", fake_processlist)

    rs = await engine.collect_sql_activity(limit=10, min_duration_ms=1000)

    assert rs.rows[0]["duration_ms"] == 1200
