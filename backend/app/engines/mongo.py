"""
MongoDB 引擎实现。

安全修复 P0-1：
原始问题：subprocess.Popen(cmd, shell=True) 将用户输入拼入 shell 命令字符串，
          攻击者可通过 ; 或 | 执行任意系统命令。
修复方案：使用 pymongo 官方 Python Driver，彻底移除 subprocess 调用。
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from bson import json_util
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.security import decrypt_field
from app.engines.models import ResultSet, ReviewSet, SqlItem

if TYPE_CHECKING:
    from app.models.instance import Instance

logger = logging.getLogger(__name__)


class MongoEngine:
    """MongoDB 数据库引擎（pymongo 驱动，无 shell 命令）。"""

    name = "MongoEngine"
    db_type = "mongo"

    def __init__(self, instance: Instance) -> None:
        self.instance = instance
        self._host = instance.host
        self._port = instance.port
        self._user = decrypt_field(instance.user)
        self._password = decrypt_field(instance.password)
        self._client: AsyncIOMotorClient | None = None

    async def get_connection(self, db_name: str | None = None) -> AsyncIOMotorClient:
        if self._client is None:
            uri = (
                f"mongodb://{self._user}:{self._password}@{self._host}:{self._port}"
                if self._user
                else f"mongodb://{self._host}:{self._port}"
            )
            self._client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        return self._client

    async def test_connection(self) -> ResultSet:
        rs = ResultSet()
        try:
            client = await self.get_connection()
            await client.admin.command("ping")
            rs.rows = [{"result": "ok"}]
            rs.column_list = ["result"]
        except Exception as e:
            rs.error = str(e)
        return rs

    def escape_string(self, value: str) -> str:
        return value  # MongoDB 用 Driver API，无需 SQL 转义

    async def get_all_databases(self) -> ResultSet:
        rs = ResultSet()
        try:
            client = await self.get_connection()
            dbs = await client.list_database_names()
            rs.rows = [(db,) for db in dbs]
            rs.column_list = ["Database"]
        except Exception as e:
            rs.error = str(e)
        return rs

    async def get_all_tables(self, db_name: str, **kwargs: Any) -> ResultSet:
        """MongoDB 中 table = collection。"""
        rs = ResultSet()
        try:
            client = await self.get_connection()
            db = client[db_name]
            colls = await db.list_collection_names()
            rs.rows = [(c,) for c in colls]
            rs.column_list = ["Collection"]
        except Exception as e:
            rs.error = str(e)
        return rs

    async def get_all_columns_by_tb(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        """采样获取集合字段（MongoDB 无固定 schema）。"""
        rs = ResultSet()
        try:
            client = await self.get_connection()
            coll = client[db_name][tb_name]
            sample = await coll.find_one()
            if sample:
                rs.column_list = ["field", "type"]
                rs.rows = [(k, type(v).__name__) for k, v in sample.items()]
        except Exception as e:
            rs.error = str(e)
        return rs

    async def describe_table(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        return await self.get_all_columns_by_tb(db_name, tb_name)

    async def get_tables_metas_data(
        self, db_name: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        result = []
        try:
            client = await self.get_connection()
            db = client[db_name]
            colls = await db.list_collection_names()
            for name in colls:
                stats = await db.command("collStats", name)
                result.append({
                    "table_name": name,
                    "count": stats.get("count", 0),
                    "data_size": stats.get("size", 0),
                    "index_size": stats.get("totalIndexSize", 0),
                    "total_size": stats.get("storageSize", 0) + stats.get("totalIndexSize", 0),
                    "storage_size": stats.get("storageSize", 0),
                })
        except Exception as e:
            logger.warning("mongo_meta_error: %s", str(e))
        return result

    # ── 查询（核心安全修复）────────────────────────────────────

    def _parse_mongo_query(self, sql: str) -> dict[str, Any]:
        """
        安全解析 MongoDB 查询语句（JS 风格 → Python dict）。
        
        支持格式：
          db.collection.find({query}, {projection})
          db.collection.aggregate([pipeline])
          db.collection.count({query})
        
        使用正则 + ast.literal_eval 安全解析，不执行任何 shell 命令或 eval。
        """
        sql = sql.strip()

        # 注入字符检测：分号/管道/反引号均视为非法格式
        for ch in (';', '|', '`'):
            if ch in sql:
                raise ValueError("不支持的 MongoDB 查询格式")

        # 匹配 db.collection.find({...}) 或 db.collection.find({...}, {...})
        find_match = re.match(
            r"db\.(\w+)\.find\((.+?)(?:,\s*(\{.+\}))?\s*\)$",
            sql, re.DOTALL
        )
        if find_match:
            collection = find_match.group(1)
            filter_str = find_match.group(2).strip()
            projection_str = find_match.group(3)

            try:
                filter_dict = json.loads(filter_str) if filter_str not in ("{}", "") else {}
            except json.JSONDecodeError:
                filter_dict = {}

            projection = {}
            if projection_str:
                try:
                    projection = json.loads(projection_str)
                except json.JSONDecodeError:
                    projection = {}

            return {"type": "find", "collection": collection,
                    "filter": filter_dict, "projection": projection}

        # 匹配 db.collection.aggregate([...])
        agg_match = re.match(r"db\.(\w+)\.aggregate\(\[(.+)\]\)$", sql, re.DOTALL)
        if agg_match:
            collection = agg_match.group(1)
            pipeline_str = f"[{agg_match.group(2)}]"
            try:
                pipeline = json.loads(pipeline_str)
            except json.JSONDecodeError:
                pipeline = []
            return {"type": "aggregate", "collection": collection, "pipeline": pipeline}

        # 匹配 db.collection.count({...})
        count_match = re.match(r"db\.(\w+)\.count\((.+)?\)$", sql, re.DOTALL)
        if count_match:
            collection = count_match.group(1)
            filter_str = (count_match.group(2) or "{}").strip()
            try:
                filter_dict = json.loads(filter_str)
            except json.JSONDecodeError:
                filter_dict = {}
            return {"type": "count", "collection": collection, "filter": filter_dict}

        raise ValueError(
            "不支持的 MongoDB 查询格式。支持格式：\n"
            "  db.collection.find({query})\n"
            "  db.collection.aggregate([pipeline])\n"
            "  db.collection.count({query})"
        )

    def query_check(self, db_name: str, sql: str) -> dict[str, Any]:
        result: dict[str, Any] = {"msg": "", "syntax_error": False}
        try:
            self._parse_mongo_query(sql)
        except ValueError as e:
            result["syntax_error"] = True
            result["msg"] = str(e)
        return result

    def filter_sql(self, sql: str, limit_num: int) -> str:
        return sql  # MongoDB 在 query() 中通过 limit() 控制

    async def query(
        self,
        db_name: str,
        sql: str,
        limit_num: int = 100,
        parameters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ResultSet:
        """
        执行 MongoDB 查询。
        
        使用 pymongo 官方 Driver，完全移除 subprocess/shell 调用（修复 P0-1）。
        """
        rs = ResultSet()
        start = time.monotonic()
        try:
            parsed = self._parse_mongo_query(sql)
            client = await self.get_connection()
            db = client[db_name]
            coll_name = parsed["collection"]

            if parsed["type"] == "find":
                cursor = db[coll_name].find(
                    parsed.get("filter", {}),
                    parsed.get("projection") or None,
                )
                if limit_num > 0:
                    cursor = cursor.limit(limit_num)
                docs = await cursor.to_list(length=limit_num or None)

            elif parsed["type"] == "aggregate":
                cursor = db[coll_name].aggregate(parsed["pipeline"])
                docs = await cursor.to_list(length=limit_num or 1000)

            elif parsed["type"] == "count":
                count = await db[coll_name].count_documents(parsed.get("filter", {}))
                rs.column_list = ["count"]
                rs.rows = [(count,)]
                rs.affected_rows = 1
                return rs

            else:
                rs.error = f"不支持的操作类型：{parsed['type']}"
                return rs

            # 序列化为 JSON 字符串（bson 支持 ObjectId / datetime 等类型）
            rs.column_list = ["document"]
            rs.rows = [(json_util.dumps(doc, ensure_ascii=False),) for doc in docs]
            rs.affected_rows = len(rs.rows)

        except ValueError as e:
            rs.error = str(e)
        except Exception as e:
            rs.error = str(e)
            logger.warning("mongo_query_error: %s", str(e))
        finally:
            rs.cost_time = int((time.monotonic() - start) * 1000)

        return rs

    def query_masking(self, db_name: str, sql: str, resultset: ResultSet) -> ResultSet:
        return resultset  # 由 services.masking 处理

    async def execute_check(self, db_name: str, sql: str) -> ReviewSet:
        """MongoDB 基础审核：验证语法是否可解析。"""
        review = ReviewSet(full_sql=sql)
        try:
            self._parse_mongo_query(sql)
            item = SqlItem(sql=sql, stagestatus="Audit completed")
            review.append(item)
        except ValueError as e:
            item = SqlItem(sql=sql, errlevel=2, errormessage=str(e))
            review.append(item)
        return review

    async def execute(self, db_name: str, sql: str, **kwargs: Any) -> ReviewSet:
        """MongoDB 写操作执行（insertOne / updateOne / deleteOne 等）。"""
        # TODO Sprint 3: 实现 MongoDB 写操作
        review = ReviewSet(full_sql=sql)
        review.error = "MongoDB 写操作将在 Sprint 3 实现"
        return review

    async def execute_workflow(self, workflow: Any) -> ReviewSet:
        return await self.execute("", getattr(workflow, "sql_content", ""))

    async def collect_metrics(self) -> dict[str, Any]:
        try:
            client = await self.get_connection()
            db = client[self.instance.db_name or "admin"]
            server_status = await db.command("serverStatus")
            return {
                "health": {"up": 1},
                "connections": {
                    "current": server_status.get("connections", {}).get("current", 0),
                    "available": server_status.get("connections", {}).get("available", 0),
                },
                "opcounters": server_status.get("opcounters", {}),
                "memory": {
                    "resident_mb": server_status.get("mem", {}).get("resident", 0),
                    "virtual_mb": server_status.get("mem", {}).get("virtual", 0),
                },
                "replication": {
                    "is_primary": server_status.get("repl", {}).get("ismaster", False),
                    "set_name": server_status.get("repl", {}).get("setName", "standalone"),
                },
            }
        except Exception as e:
            return {"health": {"up": 0}, "error": str(e)}

    async def processlist(self, **kwargs: Any) -> ResultSet:
        """查看 MongoDB 当前运行操作。"""
        rs = ResultSet()
        try:
            client = await self.get_connection()
            db = client["admin"]
            result = await db.command("currentOp", {"active": True})
            ops = result.get("inprog", [])
            rs.column_list = ["opid", "type", "ns", "secs_running", "desc"]
            rs.rows = [
                (
                    str(op.get("opid", "")),
                    op.get("type", ""),
                    op.get("ns", ""),
                    str(op.get("secs_running", 0)),
                    op.get("desc", ""),
                )
                for op in ops[:50]
            ]
        except Exception as e:
            rs.error = str(e)
        return rs

    def get_supported_metric_groups(self) -> list[str]:
        return ["health", "connections", "opcounters", "memory", "replication"]
