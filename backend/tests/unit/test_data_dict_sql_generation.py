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

        assert "information_schema.table_constraints" in captured["sql"]
        assert "information_schema.key_column_usage" in captured["sql"]
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
        assert captured["params"] == {"owner": "HR", "table_name": "USERS"}

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
        assert captured["params"] == {"owner": "HR", "table_name": "USERS"}


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
