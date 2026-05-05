"""
MongoDB 引擎单元测试。
验证 shell=True 命令注入漏洞（P0-1）修复：
所有查询通过 pymongo Driver，不调用任何 subprocess。
"""
import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.engines.mongo import MongoEngine


class MockInstance:
    host = "localhost"
    port = 27017
    user = ""       # 空表示不加密
    password = ""
    db_name = ""
    show_db_name_regex = ""


class TestMongoQueryParser:
    """测试 MongoDB 查询语句安全解析（不经过 shell）。"""

    def setup_method(self):
        self.engine = MongoEngine(instance=MockInstance())

    def test_parse_find_simple(self):
        parsed = self.engine._parse_mongo_query(
            'db.users.find({"status": "active"})'
        )
        assert parsed["type"] == "find"
        assert parsed["collection"] == "users"
        assert parsed["filter"] == {"status": "active"}

    def test_parse_find_empty_filter(self):
        parsed = self.engine._parse_mongo_query("db.users.find({})")
        assert parsed["type"] == "find"
        assert parsed["filter"] == {}

    def test_parse_find_with_projection(self):
        parsed = self.engine._parse_mongo_query(
            'db.users.find({"age": {"$gt": 18}}, {"name": 1, "email": 1})'
        )
        assert parsed["type"] == "find"
        assert parsed["projection"] == {"name": 1, "email": 1}

    def test_parse_aggregate(self):
        parsed = self.engine._parse_mongo_query(
            'db.orders.aggregate([{"$match": {"status": "paid"}}, {"$group": {"_id": "$user_id"}}])'
        )
        assert parsed["type"] == "aggregate"
        assert parsed["collection"] == "orders"
        assert len(parsed["pipeline"]) == 2

    def test_parse_count(self):
        parsed = self.engine._parse_mongo_query(
            'db.users.count({"active": true})'
        )
        assert parsed["type"] == "count"
        assert parsed["collection"] == "users"

    def test_injection_attempt_semicolon(self):
        """验证分号注入无效（不通过 shell 执行）。"""
        # 攻击向量：; rm -rf /（shell 注入）
        # 修复后：_parse_mongo_query 只解析 MongoDB 语法，
        # 不传给 shell，分号无法造成命令注入
        with pytest.raises(ValueError, match="不支持的 MongoDB 查询格式"):
            self.engine._parse_mongo_query(
                "db.users.find({}); rm -rf /"
            )

    def test_injection_attempt_pipe(self):
        """验证管道符注入无效。"""
        with pytest.raises(ValueError, match="不支持的 MongoDB 查询格式"):
            self.engine._parse_mongo_query(
                "db.users.find({}) | cat /etc/passwd"
            )

    def test_injection_attempt_backtick(self):
        """验证反引号命令替换无效。"""
        with pytest.raises(ValueError, match="不支持的 MongoDB 查询格式"):
            self.engine._parse_mongo_query(
                "db.users.find(`whoami`)"
            )

    def test_unsupported_operation_raises(self):
        """不支持的操作类型应该抛出 ValueError，而不是尝试执行。"""
        with pytest.raises(ValueError):
            self.engine._parse_mongo_query("db.users.drop()")

    def test_no_subprocess_called(self):
        """验证 MongoEngine 不调用任何 subprocess（核心安全保证）。"""
        import unittest.mock as mock

        with mock.patch("subprocess.Popen") as mock_popen:
            with contextlib.suppress(Exception):
                self.engine._parse_mongo_query('db.users.find({"id": 1})')
            # subprocess.Popen 不应该被调用
            mock_popen.assert_not_called()

    def test_query_check_valid(self):
        result = self.engine.query_check("testdb", 'db.users.find({"age": 18})')
        assert result["syntax_error"] is False
        assert result["msg"] == ""

    def test_query_check_invalid(self):
        result = self.engine.query_check("testdb", "INVALID QUERY")
        assert result["syntax_error"] is True
        assert result["msg"] != ""

    def test_parse_insert_one_write(self):
        parsed = self.engine._parse_mongo_write(
            'db.users.insertOne({"name": "Alice", "active": true})'
        )

        assert parsed["operation"] == "insertOne"
        assert parsed["collection"] == "users"
        assert parsed["args"] == [{"name": "Alice", "active": True}]

    def test_parse_update_many_write(self):
        parsed = self.engine._parse_mongo_write(
            'db.users.updateMany({"active": true}, {"$set": {"status": "ok"}})'
        )

        assert parsed["operation"] == "updateMany"
        assert parsed["args"][0] == {"active": True}
        assert parsed["args"][1] == {"$set": {"status": "ok"}}

    @pytest.mark.asyncio
    async def test_execute_check_rejects_read_query(self):
        review = await self.engine.execute_check("app", 'db.users.find({"active": true})')

        assert review.error_count == 1
        assert "不支持" in review.rows[0].errormessage

    @pytest.mark.asyncio
    async def test_execute_insert_one_uses_driver(self, monkeypatch):
        coll = SimpleNamespace(
            insert_one=AsyncMock(return_value=SimpleNamespace(inserted_id="abc123"))
        )
        monkeypatch.setattr(self.engine, "get_connection", AsyncMock(return_value=_Client(coll)))

        review = await self.engine.execute("app", 'db.users.insertOne({"name": "Alice"})')

        assert review.is_executed is True
        assert review.error_count == 0
        assert review.rows[0].affected_rows == 1
        coll.insert_one.assert_awaited_once_with({"name": "Alice"})

    @pytest.mark.asyncio
    async def test_execute_update_many_reports_modified_count(self, monkeypatch):
        coll = SimpleNamespace(
            update_many=AsyncMock(
                return_value=SimpleNamespace(matched_count=5, modified_count=3)
            )
        )
        monkeypatch.setattr(self.engine, "get_connection", AsyncMock(return_value=_Client(coll)))

        review = await self.engine.execute(
            "app",
            'db.users.updateMany({"active": true}, {"$set": {"status": "ok"}})',
        )

        assert review.is_executed is True
        assert review.rows[0].affected_rows == 3
        assert "Matched 5" in review.rows[0].stagestatus
        coll.update_many.assert_awaited_once_with(
            {"active": True}, {"$set": {"status": "ok"}}
        )

    @pytest.mark.asyncio
    async def test_execute_delete_one_reports_deleted_count(self, monkeypatch):
        coll = SimpleNamespace(
            delete_one=AsyncMock(return_value=SimpleNamespace(deleted_count=1))
        )
        monkeypatch.setattr(self.engine, "get_connection", AsyncMock(return_value=_Client(coll)))

        review = await self.engine.execute("app", 'db.users.deleteOne({"id": 1})')

        assert review.is_executed is True
        assert review.rows[0].affected_rows == 1
        coll.delete_one.assert_awaited_once_with({"id": 1})

    @pytest.mark.asyncio
    async def test_execute_workflow_uses_workflow_database(self):
        self.engine.execute = AsyncMock(return_value=SimpleNamespace(is_executed=True))
        workflow = SimpleNamespace(
            db_name="app",
            content=SimpleNamespace(sql_content='db.users.deleteOne({"id": 1})'),
        )

        await self.engine.execute_workflow(workflow)

        self.engine.execute.assert_awaited_once_with("app", 'db.users.deleteOne({"id": 1})')


class _Database:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        return self.collection


class _Client:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        return _Database(self.collection)
