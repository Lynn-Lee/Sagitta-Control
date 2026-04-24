"""
关系型数据库数据字典 SQL 生成测试。

覆盖元数据查询是否命中了正确的系统视图、关键字段与参数传递方式。
"""

from app.engines.models import ResultSet
from app.engines.mssql import MssqlEngine
from app.engines.mysql import MysqlEngine
from app.engines.oracle import OracleEngine
from app.engines.pgsql import PgSQLEngine


class MockInstance:
    host = "localhost"
    port = 3306
    user = ""
    password = ""
    db_name = "testdb"
    show_db_name_regex = ""


class MockPgInstance:
    host = "localhost"
    port = 5432
    user = ""
    password = ""
    db_name = "postgres"
    show_db_name_regex = ""


class MockOracleInstance:
    host = "localhost"
    port = 1521
    user = ""
    password = ""
    db_name = "FREEPDB1"
    show_db_name_regex = ""


class MockMssqlInstance:
    host = "localhost"
    port = 1433
    user = ""
    password = ""
    db_name = "master"
    show_db_name_regex = ""


class TestMysqlDataDictSql:
    async def test_get_table_constraints_uses_information_schema(self, monkeypatch):
        engine = MysqlEngine(instance=MockInstance())
        captured: dict = {}

        async def fake_query(db_name, sql, limit_num=0, parameters=None, **kwargs):
            captured["db_name"] = db_name
            captured["sql"] = sql
            captured["parameters"] = parameters
            return ResultSet()

        monkeypatch.setattr(engine, "query", fake_query)

        await engine.get_table_constraints("demo", "users")

        assert "information_schema.TABLE_CONSTRAINTS" in captured["sql"]
        assert "information_schema.KEY_COLUMN_USAGE" in captured["sql"]
        assert captured["parameters"] == {"db": "demo", "tb": "users"}

    async def test_get_table_indexes_uses_statistics(self, monkeypatch):
        engine = MysqlEngine(instance=MockInstance())
        captured: dict = {}

        async def fake_query(db_name, sql, limit_num=0, parameters=None, **kwargs):
            captured["db_name"] = db_name
            captured["sql"] = sql
            captured["parameters"] = parameters
            return ResultSet()

        monkeypatch.setattr(engine, "query", fake_query)

        await engine.get_table_indexes("demo", "orders")

        assert "information_schema.STATISTICS" in captured["sql"]
        assert "GROUP_CONCAT" in captured["sql"]
        assert captured["parameters"] == {"db": "demo", "tb": "orders"}


class TestPgsqlDataDictSql:
    async def test_get_table_constraints_uses_information_schema(self, monkeypatch):
        engine = PgSQLEngine(instance=MockPgInstance())
        captured: dict = {}

        async def fake_raw_query(db_name, sql, args):
            captured["db_name"] = db_name
            captured["sql"] = sql
            captured["args"] = args
            return ResultSet()

        monkeypatch.setattr(engine, "_raw_query", fake_raw_query)

        await engine.get_table_constraints("analytics", "users", schema="public")

        assert "FROM pg_constraint con" in captured["sql"]
        assert "JOIN pg_class tbl" in captured["sql"]
        assert "pg_get_constraintdef" in captured["sql"]
        assert captured["args"] == ["public", "users"]

    async def test_get_table_indexes_uses_pg_indexes(self, monkeypatch):
        engine = PgSQLEngine(instance=MockPgInstance())
        captured: dict = {}

        async def fake_raw_query(db_name, sql, args):
            captured["db_name"] = db_name
            captured["sql"] = sql
            captured["args"] = args
            return ResultSet()

        monkeypatch.setattr(engine, "_raw_query", fake_raw_query)

        await engine.get_table_indexes("analytics", "users", schema="public")

        assert "FROM pg_indexes" in captured["sql"]
        assert "indexdef AS index_definition" in captured["sql"]
        assert "indexdef ILIKE" in captured["sql"]
        assert captured["args"] == ["public", "users"]


class TestOracleDataDictSql:
    async def test_get_table_constraints_uses_all_constraints(self, monkeypatch):
        engine = OracleEngine(instance=MockOracleInstance())
        captured: dict = {}

        def fake_run_query_sync(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return ResultSet()

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)
        monkeypatch.setattr("app.engines.oracle.asyncio.to_thread", fake_to_thread)

        await engine.get_table_constraints("HR", "USERS")

        assert "FROM all_constraints c" in captured["sql"]
        assert "JOIN all_cons_columns cols" in captured["sql"]
        assert "CASE c.constraint_type" in captured["sql"]
        assert "c.search_condition_vc" in captured["sql"]
        assert captured["params"] == {"owner": "HR", "table_name": "USERS"}

    async def test_get_table_constraints_falls_back_to_user_constraints(self, monkeypatch):
        engine = OracleEngine(instance=MockOracleInstance())
        calls: list[tuple[str, dict | None]] = []

        def fake_run_query_sync(sql, params=None):
            calls.append((sql, params))
            if len(calls) == 1:
                return ResultSet(error="ORA-00942")
            return ResultSet()

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)
        monkeypatch.setattr("app.engines.oracle.asyncio.to_thread", fake_to_thread)

        await engine.get_table_constraints("HR", "USERS")

        assert "FROM all_constraints c" in calls[0][0]
        assert calls[0][1] == {"owner": "HR", "table_name": "USERS"}
        assert "FROM user_constraints c" in calls[1][0]
        assert calls[1][1] == {"table_name": "USERS"}

    async def test_get_table_constraints_falls_back_without_search_condition_vc(
        self, monkeypatch
    ):
        engine = OracleEngine(instance=MockOracleInstance())
        calls: list[tuple[str, dict | None]] = []

        def fake_run_query_sync(sql, params=None):
            calls.append((sql, params))
            if len(calls) < 3:
                return ResultSet(error="ORA-00904: invalid identifier")
            return ResultSet()

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)
        monkeypatch.setattr("app.engines.oracle.asyncio.to_thread", fake_to_thread)

        await engine.get_table_constraints("HR", "USERS")

        assert "c.search_condition_vc" in calls[0][0]
        assert "c.search_condition_vc" in calls[1][0]
        assert "c.search_condition_vc" not in calls[2][0]
        assert "'' AS check_clause" in calls[2][0]

    async def test_get_table_indexes_uses_all_indexes(self, monkeypatch):
        engine = OracleEngine(instance=MockOracleInstance())
        captured: dict = {}

        def fake_run_query_sync(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return ResultSet()

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)
        monkeypatch.setattr("app.engines.oracle.asyncio.to_thread", fake_to_thread)

        await engine.get_table_indexes("HR", "USERS")

        assert "FROM all_indexes i" in captured["sql"]
        assert "JOIN all_ind_columns cols" in captured["sql"]
        assert "LEFT JOIN all_constraints c" in captured["sql"]
        assert "PRIMARY KEY INDEX" in captured["sql"]
        assert captured["params"] == {"owner": "HR", "table_name": "USERS"}

    async def test_get_table_indexes_falls_back_to_user_indexes(self, monkeypatch):
        engine = OracleEngine(instance=MockOracleInstance())
        calls: list[tuple[str, dict | None]] = []

        def fake_run_query_sync(sql, params=None):
            calls.append((sql, params))
            if len(calls) == 1:
                return ResultSet(error="ORA-00942")
            return ResultSet()

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)
        monkeypatch.setattr("app.engines.oracle.asyncio.to_thread", fake_to_thread)

        await engine.get_table_indexes("HR", "USERS")

        assert "FROM all_indexes i" in calls[0][0]
        assert calls[0][1] == {"owner": "HR", "table_name": "USERS"}
        assert "FROM user_indexes i" in calls[1][0]
        assert calls[1][1] == {"table_name": "USERS"}


class TestMssqlDataDictSql:
    async def test_get_table_constraints_uses_information_schema(self, monkeypatch):
        engine = MssqlEngine(instance=MockMssqlInstance())
        captured: dict = {}

        def fake_run_query_sync(sql, params=None, db_name=None):
            captured["sql"] = sql
            captured["params"] = params
            captured["db_name"] = db_name
            return ResultSet()

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)
        monkeypatch.setattr("app.engines.mssql.asyncio.to_thread", fake_to_thread)

        await engine.get_table_constraints("demo", "messages", schema="dbo")

        assert "INFORMATION_SCHEMA.TABLE_CONSTRAINTS" in captured["sql"]
        assert "INFORMATION_SCHEMA.KEY_COLUMN_USAGE" in captured["sql"]
        assert captured["params"] == ("dbo", "messages")
        assert captured["db_name"] == "demo"

    async def test_get_table_indexes_uses_sys_indexes(self, monkeypatch):
        engine = MssqlEngine(instance=MockMssqlInstance())
        captured: dict = {}

        def fake_run_query_sync(sql, params=None, db_name=None):
            captured["sql"] = sql
            captured["params"] = params
            captured["db_name"] = db_name
            return ResultSet()

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)
        monkeypatch.setattr("app.engines.mssql.asyncio.to_thread", fake_to_thread)

        await engine.get_table_indexes("demo", "messages", schema="dbo")

        assert "FROM sys.indexes i" in captured["sql"]
        assert "JOIN sys.index_columns ic" in captured["sql"]
        assert captured["params"] == ("dbo", "messages")
        assert captured["db_name"] == "demo"
