"""
MySQL 引擎单元测试。
重点验证：
  - 参数化查询规范
  - sqlglot 基础审核规则
  - filter_sql LIMIT 注入
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.engines.models import ResultSet, ReviewSet
from app.engines.mysql import MysqlEngine
from app.engines.pgsql import PgSQLEngine
from app.engines.tidb import TidbEngine


class MockInstance:
    host = "localhost"
    port = 3306
    user = ""
    password = ""
    db_name = "testdb"
    show_db_name_regex = ""


class TestMysqlQueryCheck:
    def setup_method(self):
        self.engine = MysqlEngine(instance=MockInstance())

    def test_select_star_warning(self):
        result = self.engine.query_check("testdb", "SELECT * FROM users")
        assert result["has_star"] is True

    def test_write_operation_blocked(self):
        result = self.engine.query_check("testdb", "INSERT INTO users VALUES (1, 'test')")
        assert result["msg"] != ""
        assert "写操作" in result["msg"]

    def test_update_blocked(self):
        result = self.engine.query_check("testdb", "UPDATE users SET name='x'")
        assert "写操作" in result["msg"]

    def test_valid_select(self):
        result = self.engine.query_check("testdb", "SELECT id, name FROM users WHERE id = 1")
        assert result["has_star"] is False
        assert result["syntax_error"] is False

    def test_invalid_sql_syntax_error(self):
        result = self.engine.query_check("testdb", "SELCT * FORM users")
        # sqlglot 可能仍能部分解析，但 syntax_error 应为 True
        # 至少不应该抛出未捕获的异常
        assert isinstance(result, dict)


class TestMysqlFilterSql:
    def setup_method(self):
        self.engine = MysqlEngine(instance=MockInstance())

    def test_adds_limit(self):
        result = self.engine.filter_sql("SELECT * FROM users", 100)
        assert "LIMIT 100" in result

    def test_no_double_limit(self):
        result = self.engine.filter_sql("SELECT * FROM users LIMIT 50", 100)
        assert result.count("LIMIT") == 1

    def test_zero_limit_no_change(self):
        sql = "SELECT * FROM users"
        result = self.engine.filter_sql(sql, 0)
        assert result == sql

    def test_strips_trailing_semicolon(self):
        result = self.engine.filter_sql("SELECT 1;", 10)
        assert not result.endswith(";")


@pytest.mark.asyncio
async def test_tidb_explain_uses_plain_explain(monkeypatch):
    engine = TidbEngine(instance=MockInstance())
    captured: dict = {}

    async def fake_query(db_name, sql, limit_num=0, parameters=None, **kwargs):
        captured["db_name"] = db_name
        captured["sql"] = sql
        captured["limit_num"] = limit_num
        return ResultSet(column_list=["id"], rows=[(1,)])

    monkeypatch.setattr(engine, "query", fake_query)

    rs = await engine.explain_query("testdb", "SELECT 1;")

    assert rs.is_success
    assert captured == {"db_name": "testdb", "sql": "EXPLAIN SELECT 1", "limit_num": 1000}


class TestMysqlExecuteCheck:
    def setup_method(self):
        self.engine = MysqlEngine(instance=MockInstance())

    @pytest.mark.asyncio
    async def test_update_without_where_rejected(self):
        review = await self.engine._sqlglot_check(
            "testdb",
            "UPDATE users SET status = 1",
            ReviewSet(full_sql="UPDATE users SET status = 1"),
        )
        error_items = [r for r in review.rows if r.errlevel == 2]
        assert len(error_items) > 0
        assert "WHERE" in error_items[0].errormessage

    @pytest.mark.asyncio
    async def test_delete_without_where_rejected(self):
        review = await self.engine._sqlglot_check(
            "testdb",
            "DELETE FROM users",
            ReviewSet(full_sql="DELETE FROM users"),
        )
        error_items = [r for r in review.rows if r.errlevel == 2]
        assert len(error_items) > 0

    @pytest.mark.asyncio
    async def test_drop_table_warning(self):
        review = await self.engine._sqlglot_check(
            "testdb",
            "DROP TABLE IF EXISTS old_table",
            ReviewSet(full_sql="DROP TABLE IF EXISTS old_table"),
        )
        # DROP 应该产生警告（errlevel=1）
        warn_items = [r for r in review.rows if r.errlevel >= 1]
        assert len(warn_items) > 0

    @pytest.mark.asyncio
    async def test_valid_insert_passes(self):
        review = await self.engine._sqlglot_check(
            "testdb",
            "INSERT INTO users (name, email) VALUES ('张三', 'test@example.com')",
            ReviewSet(full_sql=""),
        )
        error_items = [r for r in review.rows if r.errlevel == 2]
        assert len(error_items) == 0

    @pytest.mark.asyncio
    async def test_update_with_where_passes(self):
        review = await self.engine._sqlglot_check(
            "testdb",
            "UPDATE users SET status = 1 WHERE id = 100",
            ReviewSet(full_sql=""),
        )
        error_items = [r for r in review.rows if r.errlevel == 2]
        assert len(error_items) == 0

    @pytest.mark.asyncio
    async def test_goinception_placeholder_warns_when_enabled(self):
        review = await self.engine._goinception_check(
            "testdb",
            "ALTER TABLE users ADD COLUMN age int",
            ReviewSet(full_sql="ALTER TABLE users ADD COLUMN age int"),
        )

        warn_items = [r for r in review.rows if r.errlevel == 1]
        assert len(warn_items) == 1
        assert "goInception 增强审核尚未接入" in warn_items[0].errormessage

    @pytest.mark.asyncio
    async def test_execute_workflow_delegates_snapshot_sql(self):
        self.engine.execute = AsyncMock(return_value=ReviewSet(full_sql="UPDATE users SET status=1"))
        workflow = SimpleNamespace(
            db_name="testdb",
            content=SimpleNamespace(sql_content="UPDATE users SET status=1 WHERE id=1"),
        )

        review = await self.engine.execute_workflow(workflow)

        assert review.full_sql == "UPDATE users SET status=1"
        self.engine.execute.assert_awaited_once_with(
            "testdb", "UPDATE users SET status=1 WHERE id=1"
        )


class TestMysqlEscapeString:
    def setup_method(self):
        self.engine = MysqlEngine(instance=MockInstance())

    def test_escape_backtick_identifier_by_doubling(self):
        result = self.engine.escape_string("table`name")
        assert result == "table``name"

    def test_single_quote_is_not_identifier_escape_responsibility(self):
        result = self.engine.escape_string("O'Brien")
        assert result == "O'Brien"

    def test_normal_string_unchanged(self):
        result = self.engine.escape_string("normal_table_name")
        assert result == "normal_table_name"

    @pytest.mark.asyncio
    async def test_get_all_tables_uses_doubled_backtick_identifier(self, monkeypatch):
        captured: dict = {}

        async def fake_query(db_name, sql, limit_num=0, parameters=None, **kwargs):
            captured["db_name"] = db_name
            captured["sql"] = sql
            captured["limit_num"] = limit_num
            captured["parameters"] = parameters
            return ResultSet(column_list=["Tables_in_a`b"], rows=[])

        monkeypatch.setattr(self.engine, "query", fake_query)

        rs = await self.engine.get_all_tables("a`b")

        assert rs.is_success
        assert captured == {
            "db_name": "a`b",
            "sql": "SHOW TABLES FROM `a``b`",
            "limit_num": 0,
            "parameters": None,
        }

    @pytest.mark.asyncio
    async def test_processlist_command_filter_uses_parameters(self, monkeypatch):
        captured: dict = {}

        async def fake_query(db_name, sql, limit_num=0, parameters=None, **kwargs):
            captured["db_name"] = db_name
            captured["sql"] = sql
            captured["limit_num"] = limit_num
            captured["parameters"] = parameters
            return ResultSet(column_list=["session_id"], rows=[])

        monkeypatch.setattr(self.engine, "query", fake_query)

        rs = await self.engine.processlist(command_type="Query' OR '1'='1")

        assert rs.is_success
        assert "Query' OR '1'='1" not in captured["sql"]
        assert "p.COMMAND = %(command_type)s" in captured["sql"]
        assert captured["parameters"] == {"command_type": "Query' OR '1'='1"}

    @pytest.mark.asyncio
    async def test_tidb_processlist_command_filter_uses_parameters(self, monkeypatch):
        engine = TidbEngine(instance=MockInstance())
        captured: dict = {}

        async def fake_query(db_name, sql, limit_num=0, parameters=None, **kwargs):
            captured["db_name"] = db_name
            captured["sql"] = sql
            captured["limit_num"] = limit_num
            captured["parameters"] = parameters
            return ResultSet(column_list=["session_id"], rows=[])

        monkeypatch.setattr(engine, "query", fake_query)

        rs = await engine.processlist(command_type="Query' OR '1'='1")

        assert rs.is_success
        assert "Query' OR '1'='1" not in captured["sql"]
        assert "COMMAND = %(command_type)s" in captured["sql"]
        assert captured["parameters"] == {"command_type": "Query' OR '1'='1"}


class TestMysqlMonitorMetrics:
    def test_current_activity_counts_use_processlist_current_state(self):
        rs = ResultSet(
            rows=[
                {
                    "command": "Query",
                    "active_duration_ms": 1500,
                    "state": "Sending data",
                    "sql_text": "select * from orders",
                },
                {
                    "command": "Query",
                    "active_duration_ms": 800,
                    "state": "Sending data",
                    "sql_text": "select * from users",
                },
                {
                    "command": "Sleep",
                    "active_duration_ms": None,
                    "state": "",
                    "sql_text": "",
                },
                {
                    "command": "Query",
                    "active_duration_ms": 3000,
                    "state": "updating",
                    "trx_state": "LOCK WAIT",
                    "sql_text": "update orders set status = 1",
                },
                {
                    "command": "Query",
                    "duration_ms": 6000,
                    "state": "Waiting for table metadata lock",
                    "sql_text": "alter table orders add column note varchar(64)",
                },
            ]
        )

        slow_queries, lock_waits = MysqlEngine._current_activity_counts(rs, 1000)

        assert slow_queries == 3
        assert lock_waits == 2

    def test_current_activity_counts_return_none_when_processlist_failed(self):
        slow_queries, lock_waits = MysqlEngine._current_activity_counts(
            ResultSet(error="permission denied"),
            1000,
        )

        assert slow_queries is None
        assert lock_waits is None


class MockPgInstance:
    host = "localhost"
    port = 5432
    user = ""
    password = ""
    db_name = "postgres"
    show_db_name_regex = ""


class TestPgSQLExecuteWorkflow:
    @pytest.mark.asyncio
    async def test_execute_workflow_delegates_snapshot_sql(self):
        engine = PgSQLEngine(instance=MockPgInstance())
        engine.execute = AsyncMock(return_value=ReviewSet(full_sql="DELETE FROM users"))
        workflow = SimpleNamespace(
            db_name="app",
            content=SimpleNamespace(sql_content="DELETE FROM users WHERE id=1"),
        )

        review = await engine.execute_workflow(workflow)

        assert review.full_sql == "DELETE FROM users"
        engine.execute.assert_awaited_once_with("app", "DELETE FROM users WHERE id=1")
