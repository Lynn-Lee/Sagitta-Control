"""Elasticsearch 引擎单元测试。"""

import pytest

from app.engines.elasticsearch import ElasticsearchEngine, OpenSearchEngine


class MockInstance:
    db_type = "elasticsearch"
    host = "localhost"
    port = 9200
    user = ""
    password = ""
    db_name = ""
    show_db_name_regex = ""


class FakeCat:
    async def indices(self, index, format, h):
        assert format == "json"
        assert "index" in h
        return [
            {"index": "orders-2026", "health": "green", "status": "open", "docs.count": "10", "store.size": "1mb"},
            {"index": "users", "health": "yellow", "status": "open", "docs.count": "3", "store.size": "256kb"},
        ]


class FakeIndices:
    async def get_mapping(self, index):
        assert index == "orders*"
        return {
            "orders-2026": {
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "user": {"properties": {"name": {"type": "text"}}},
                    }
                }
            }
        }


class FakeSql:
    def __init__(self):
        self.payload = {}

    async def query(self, **payload):
        self.payload = payload
        return {
            "columns": [{"name": "id"}, {"name": "amount"}],
            "rows": [[1, 20]],
        }


class FakeCluster:
    async def health(self):
        return {
            "status": "green",
            "cluster_name": "es-test",
            "number_of_nodes": 3,
            "number_of_data_nodes": 2,
            "active_shards": 8,
            "unassigned_shards": 0,
        }


class FakeTasks:
    async def list(self, actions, detailed):
        assert "search" in actions
        assert detailed is True
        return {
            "nodes": {
                "node-1": {
                    "tasks": {
                        "101": {
                            "id": "node-1:101",
                            "action": "indices:data/read/search",
                            "description": "indices[orders], search_type[QUERY_THEN_FETCH]",
                            "running_time_in_nanos": 2_500_000_000,
                            "headers": {"user": "elastic", "X-Forwarded-For": "10.0.0.1"},
                        },
                        "102": {
                            "id": "node-1:102",
                            "action": "indices:data/read/search",
                            "description": "quick search",
                            "running_time_in_nanos": 100_000_000,
                        },
                    }
                }
            }
        }


class FakeClient:
    def __init__(self):
        self.cat = FakeCat()
        self.indices = FakeIndices()
        self.sql = FakeSql()
        self.cluster = FakeCluster()
        self.tasks = FakeTasks()

    async def info(self):
        return {"cluster_name": "es-test", "version": {"number": "8.12.2"}}


def _engine() -> ElasticsearchEngine:
    engine = ElasticsearchEngine(MockInstance())
    engine._client = FakeClient()
    return engine


def test_elasticsearch_query_check_blocks_write_operation():
    engine = _engine()

    result = engine.query_check("", "DELETE FROM orders WHERE id = 1")

    assert "不允许" in result["msg"]


def test_elasticsearch_query_check_detects_select_star():
    engine = _engine()

    result = engine.query_check("", "SELECT * FROM orders")

    assert result["has_star"] is True
    assert result["syntax_error"] is False


@pytest.mark.asyncio
async def test_elasticsearch_lists_indices_as_tables():
    rs = await _engine().get_all_tables("orders")

    assert rs.is_success
    assert rs.rows[0]["index"] == "orders-2026"
    assert rs.column_list == ["index", "health", "status", "docs_count", "store_size"]


@pytest.mark.asyncio
async def test_elasticsearch_flattens_mapping_columns():
    rs = await _engine().get_all_columns_by_tb("", "orders")

    paths = {row["path"]: row["type"] for row in rs.rows}
    assert paths["id"] == "keyword"
    assert paths["user"] == "object"
    assert paths["user.name"] == "text"


@pytest.mark.asyncio
async def test_elasticsearch_exposes_mapping_fields_as_indexes():
    rs = await _engine().get_table_indexes("", "orders")

    index_names = {row["index_name"]: row["index_type"] for row in rs.rows}
    assert index_names["id"] == "KEYWORD FIELD"
    assert "user" not in index_names
    assert index_names["user.name"] == "TEXT FIELD"


@pytest.mark.asyncio
async def test_elasticsearch_constraints_are_empty_with_warning():
    rs = await _engine().get_table_constraints("", "orders")

    assert rs.is_success
    assert rs.rows == []
    assert "不提供关系型约束" in rs.warning


@pytest.mark.asyncio
async def test_elasticsearch_query_uses_sql_api_and_limit():
    engine = _engine()

    rs = await engine.query("", "SELECT id, amount FROM orders", limit_num=10)

    assert rs.column_list == ["id", "amount"]
    assert rs.rows == [[1, 20]]
    assert engine._client.sql.payload["query"].endswith("LIMIT 10")
    assert engine._client.sql.payload["fetch_size"] == 10


@pytest.mark.asyncio
async def test_elasticsearch_collects_basic_metrics():
    metrics = await _engine().collect_metrics()

    assert metrics["health"]["up"] == 1
    assert metrics["health"]["status"] == "green"
    assert metrics["cluster"]["nodes"] == 3
    assert metrics["indices"]["count"] == 2
    assert metrics["indices"]["docs_count"] == 13


@pytest.mark.asyncio
async def test_elasticsearch_collects_running_search_tasks_as_activity():
    rs = await _engine().collect_sql_activity(limit=10, min_duration_ms=1000)

    assert rs.rows == [
        {
            "source": "elasticsearch_activity",
            "source_ref": "node-1:101",
            "db_name": "",
            "sql_text": "indices[orders], search_type[QUERY_THEN_FETCH]",
            "duration_ms": 2500,
            "username": "elastic",
            "client_host": "10.0.0.1",
            "command": "indices:data/read/search",
            "state": "running",
        }
    ]


def test_opensearch_engine_is_registered_compatible_class():
    engine = OpenSearchEngine(MockInstance())

    assert engine.name == "OpenSearchEngine"
    assert engine.db_type == "opensearch"
