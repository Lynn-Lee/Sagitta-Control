"""Cassandra 引擎单元测试。"""

from __future__ import annotations

from collections import namedtuple
from types import SimpleNamespace

import pytest

from app.engines.cassandra import CassandraEngine


class MockInstance:
    db_type = "cassandra"
    host = "node1,node2"
    port = 9042
    user = ""
    password = ""
    db_name = "app"
    show_db_name_regex = ""


class FakeResult:
    def __init__(self, rows, column_names=None):
        self.current_rows = rows
        self.column_names = column_names


class FakeSession:
    def __init__(self, cluster, result=None):
        self.cluster = cluster
        self.result = result or FakeResult([], [])
        self.executed = []
        self.closed = False

    def execute(self, sql, parameters=None):
        self.executed.append((sql, parameters))
        return self.result

    def shutdown(self):
        self.closed = True


class FakeCluster:
    def __init__(self):
        self.closed = False
        self.metadata = SimpleNamespace(
            keyspaces={
                "app": SimpleNamespace(
                    tables={
                        "orders": SimpleNamespace(
                            columns={
                                "id": SimpleNamespace(cql_type="uuid"),
                                "created_at": SimpleNamespace(cql_type="timestamp"),
                                "amount": SimpleNamespace(cql_type="decimal"),
                            },
                            partition_key=[SimpleNamespace(name="id")],
                            clustering_key=[SimpleNamespace(name="created_at")],
                            export_as_string=lambda: "CREATE TABLE app.orders (id uuid PRIMARY KEY)",
                        )
                    }
                ),
                "system": SimpleNamespace(tables={}),
            }
        )

    def shutdown(self):
        self.closed = True


def _engine() -> CassandraEngine:
    return CassandraEngine(MockInstance())


def test_cassandra_query_check_blocks_write_operation():
    result = _engine().query_check("app", "DELETE FROM orders WHERE id = ?")

    assert "不允许" in result["msg"]


def test_cassandra_query_check_detects_select_star():
    result = _engine().query_check("app", "SELECT * FROM orders")

    assert result["has_star"] is True
    assert result["syntax_error"] is False


def test_cassandra_adds_limit_to_select_only():
    engine = _engine()

    assert engine.filter_sql("SELECT id FROM orders", 20).endswith("LIMIT 20")
    assert engine.filter_sql("DESCRIBE TABLE orders", 20) == "DESCRIBE TABLE orders"
    assert engine.query_check("app", "DESCRIBE TABLE orders")["syntax_error"] is True


@pytest.mark.asyncio
async def test_cassandra_lists_non_system_keyspaces(monkeypatch):
    engine = _engine()
    cluster = FakeCluster()
    monkeypatch.setattr(engine, "_connect_sync", lambda db_name=None: FakeSession(cluster))

    rs = await engine.get_all_databases()

    assert rs.is_success
    assert rs.rows == [("app",)]


@pytest.mark.asyncio
async def test_cassandra_reads_table_columns_from_metadata(monkeypatch):
    engine = _engine()
    cluster = FakeCluster()
    monkeypatch.setattr(engine, "_connect_sync", lambda db_name=None: FakeSession(cluster))

    rs = await engine.get_all_columns_by_tb("app", "orders")

    assert rs.is_success
    assert rs.rows[0]["column_name"] == "id"
    assert rs.rows[0]["kind"] == "partition_key"
    assert rs.rows[1]["kind"] == "clustering_key"
    assert rs.rows[2]["column_type"] == "decimal"


@pytest.mark.asyncio
async def test_cassandra_exposes_key_metadata_as_constraints_and_indexes(monkeypatch):
    engine = _engine()
    cluster = FakeCluster()
    monkeypatch.setattr(engine, "_connect_sync", lambda db_name=None: FakeSession(cluster))

    constraints = await engine.get_table_constraints("app", "orders")
    indexes = await engine.get_table_indexes("app", "orders")

    assert constraints.column_list[0] == "constraint_name"
    assert constraints.rows == [
        {
            "constraint_name": "orders_partition_key",
            "constraint_type": "PARTITION KEY",
            "column_names": "id",
            "referenced_table_name": "",
            "referenced_column_names": "",
            "check_clause": "",
        },
        {
            "constraint_name": "orders_clustering_key",
            "constraint_type": "CLUSTERING KEY",
            "column_names": "created_at",
            "referenced_table_name": "",
            "referenced_column_names": "",
            "check_clause": "",
        },
    ]
    assert indexes.rows[0]["index_type"] == "PARTITION KEY"
    assert indexes.rows[1]["index_type"] == "CLUSTERING KEY"


@pytest.mark.asyncio
async def test_cassandra_query_returns_named_rows_and_limit(monkeypatch):
    engine = _engine()
    cluster = FakeCluster()
    row_type = namedtuple("Row", ["id", "amount"])
    session = FakeSession(cluster, FakeResult([row_type("o1", 12)], ["id", "amount"]))
    monkeypatch.setattr(engine, "_connect_sync", lambda db_name=None: session)

    rs = await engine.query("app", "SELECT id, amount FROM orders", limit_num=5)

    assert rs.column_list == ["id", "amount"]
    assert rs.rows == [{"id": "o1", "amount": 12}]
    assert session.executed[0][0].endswith("LIMIT 5")


@pytest.mark.asyncio
async def test_cassandra_execute_is_disabled_until_verified():
    review = await _engine().execute_check("app", "CREATE TABLE orders (id uuid PRIMARY KEY)")

    assert review.error_count == 1
    assert "待客户同构环境验证" in review.rows[0].errormessage
