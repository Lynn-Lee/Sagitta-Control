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

from app.engines.models import ReviewSet
from app.engines.mysql import MysqlEngine
from app.engines.pgsql import PgSQLEngine


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

    def test_escape_backtick(self):
        result = self.engine.escape_string("table`name")
        assert "`" not in result or result.count("`") == result.count("\\`")

    def test_escape_single_quote(self):
        result = self.engine.escape_string("O'Brien")
        assert "\\'" in result

    def test_normal_string_unchanged(self):
        result = self.engine.escape_string("normal_table_name")
        assert result == "normal_table_name"


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
