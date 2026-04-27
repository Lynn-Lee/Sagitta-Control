from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.routers import query as query_router
from app.schemas.query import QueryExecuteRequest
from app.services.query_guard import get_query_guard
from app.services.query_priv import QueryPrivService


@pytest.mark.parametrize("db_type", ["mysql", "tidb", "pgsql", "oracle", "mssql", "starrocks", "clickhouse"])
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM users",
        "WITH recent AS (SELECT * FROM users) SELECT * FROM recent",
        "SHOW TABLES",
        "DESC users",
        "DESCRIBE users",
        "EXPLAIN SELECT * FROM users",
    ],
)
def test_sql_guards_allow_read_only_statements(db_type, sql):
    result = get_query_guard(db_type).validate(sql, "analytics")

    assert result.allowed is True
    assert result.statement_kind


@pytest.mark.parametrize("db_type", ["mysql", "pgsql", "oracle", "mssql", "starrocks", "clickhouse"])
@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO users VALUES (1)",
        "UPDATE users SET name = 'x'",
        "DELETE FROM users",
        "CREATE TABLE t (id int)",
        "ALTER TABLE users ADD COLUMN x int",
        "DROP TABLE users",
        "TRUNCATE TABLE users",
        "REPLACE INTO users VALUES (1)",
        "MERGE INTO users USING src ON users.id = src.id WHEN MATCHED THEN UPDATE SET name = src.name",
        "CALL refresh_users()",
        "GRANT SELECT ON users TO alice",
        "SET search_path = private",
        "SELECT * INTO users_copy FROM users",
        "SELECT * FROM users FOR UPDATE",
        "SELECT pg_advisory_lock(1)",
        "EXPLAIN ANALYZE SELECT * FROM users",
        "SELECT * FROM users; DROP TABLE users",
    ],
)
def test_sql_guards_reject_write_or_side_effect_statements(db_type, sql):
    result = get_query_guard(db_type).validate(sql, "analytics")

    assert result.allowed is False
    assert result.reason


def test_show_create_table_extracts_table_ref():
    result = get_query_guard("mysql").validate("SHOW CREATE TABLE users", "analytics")

    assert result.allowed is True
    assert result.table_refs == [{"schema": "analytics", "name": "users"}]


def test_explain_select_uses_underlying_table_refs():
    result = get_query_guard("pgsql").validate("EXPLAIN SELECT * FROM public.users", "analytics")

    assert result.allowed is True
    assert result.table_refs == [{"schema": "public", "name": "users"}]


def test_select_with_cte_does_not_treat_cte_alias_as_real_table():
    result = get_query_guard("mysql").validate(
        "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent",
        "analytics",
    )

    assert result.allowed is True
    assert result.table_refs == [{"schema": "analytics", "name": "orders"}]


def test_limit_is_only_applied_to_select_like_sql():
    guard = get_query_guard("mysql")

    assert guard.apply_limit("SELECT * FROM users", 100, "select").endswith("LIMIT 100")
    assert guard.apply_limit("SHOW TABLES", 100, "show") == "SHOW TABLES"
    assert guard.apply_limit("DESC users", 100, "desc") == "DESC users"


@pytest.mark.parametrize("db_type", ["doris", "cassandra", "elasticsearch", "opensearch"])
def test_unimplemented_engines_fail_closed(db_type):
    result = get_query_guard(db_type).validate("SELECT * FROM users", "analytics")

    assert result.allowed is False
    assert "暂不支持在线查询执行" in result.reason


def test_mongo_guard_rejects_side_effect_aggregate_stages():
    result = get_query_guard("mongo").validate(
        'db.users.aggregate([{"$merge": "users_copy"}])',
        "analytics",
    )

    assert result.allowed is False
    assert "aggregate" in result.reason


def test_mongo_guard_allows_find_and_extracts_collection_ref():
    result = get_query_guard("mongo").validate('db.users.find({"age": 18})', "analytics")

    assert result.allowed is True
    assert result.table_refs == [{"schema": "analytics", "name": "users"}]
    assert result.use_driver_limit is True


def test_redis_guard_rejects_write_and_dangerous_commands():
    guard = get_query_guard("redis")

    assert guard.validate("get user:1", "0").allowed is True
    assert guard.validate("set user:1 bob", "0").allowed is False
    assert guard.validate("debug object user:1", "0").allowed is False
    assert guard.validate("client list", "0").allowed is False


@pytest.mark.asyncio
async def test_desc_table_uses_table_privilege_when_guard_supplies_table_refs(monkeypatch):
    instance = SimpleNamespace(id=1, db_type="mysql", resource_groups=[SimpleNamespace(id=2)])
    monkeypatch.setattr(QueryPrivService, "_has_db_priv", AsyncMock(return_value=False))
    monkeypatch.setattr(QueryPrivService, "_has_table_priv", AsyncMock(return_value=True))

    allowed, reason = await QueryPrivService.check_query_priv(
        db=AsyncMock(),
        user={"id": 7, "permissions": [], "resource_groups": [2], "is_superuser": False},
        instance=instance,
        db_name="analytics",
        sql="DESC users",
        table_refs=[{"schema": "analytics", "name": "users"}],
    )

    assert allowed is True
    assert reason == "privilege"


@pytest.mark.asyncio
async def test_show_tables_uses_database_privilege_without_table_refs(monkeypatch):
    instance = SimpleNamespace(id=1, db_type="mysql", resource_groups=[SimpleNamespace(id=2)])
    monkeypatch.setattr(QueryPrivService, "_has_instance_priv", AsyncMock(return_value=False))
    monkeypatch.setattr(QueryPrivService, "_has_db_priv", AsyncMock(return_value=True))

    allowed, reason = await QueryPrivService.check_query_priv(
        db=AsyncMock(),
        user={"id": 7, "permissions": [], "resource_groups": [2], "is_superuser": False},
        instance=instance,
        db_name="analytics",
        sql="SHOW TABLES",
        table_refs=[],
    )

    assert allowed is True
    assert reason == "db_privilege"


@pytest.mark.asyncio
async def test_router_rejects_write_sql_before_permission_check(monkeypatch):
    instance = SimpleNamespace(id=1, db_type="mysql", resource_groups=[])
    fake_engine = MagicMock()

    monkeypatch.setattr(query_router, "_load_instance", AsyncMock(return_value=instance))
    monkeypatch.setattr(query_router, "get_engine", MagicMock(return_value=fake_engine))
    monkeypatch.setattr(QueryPrivService, "check_query_priv", AsyncMock(return_value=(True, "privilege")))

    with pytest.raises(HTTPException) as exc_info:
        await query_router._run_query_with_permissions(
            db=AsyncMock(),
            user={"id": 7, "permissions": [], "resource_groups": [], "is_superuser": False},
            data=QueryExecuteRequest(
                instance_id=1,
                db_name="analytics",
                sql="UPDATE users SET name = 'x'",
                limit_num=100,
            ),
        )

    assert exc_info.value.status_code == 400
    QueryPrivService.check_query_priv.assert_not_awaited()
    fake_engine.query.assert_not_called()
