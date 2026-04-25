"""
Redis 引擎（Pack E）。
支持：连接测试、命令执行、INFO 指标采集、KEY 浏览、慢日志查询。
安全：只允许执行白名单命令，禁止 FLUSHALL/CONFIG/SLAVEOF 等危险命令。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.core.security import decrypt_field
from app.engines.models import ResultSet, ReviewSet, SqlItem

if TYPE_CHECKING:
    from app.models.instance import Instance

logger = logging.getLogger(__name__)

# 允许在线查询执行的命令（白名单）
ALLOWED_COMMANDS = {
    "get", "mget", "hget", "hgetall", "hkeys", "hvals", "lrange", "smembers",
    "scard", "zrange", "zrangebyscore", "zcard", "ttl", "pttl", "type",
    "exists", "strlen", "llen", "sismember", "zscore", "keys", "scan",
    "hscan", "sscan", "zscan", "info", "dbsize", "time", "ping",
    "object", "debug", "slowlog", "client",
}

# 工单执行允许的额外命令
WORKFLOW_ALLOWED = {
    "set", "mset", "hset", "hmset", "lpush", "rpush", "sadd", "zadd",
    "del", "expire", "pexpire", "rename", "persist",
}


class RedisEngine:
    name = "RedisEngine"
    db_type = "redis"

    def __init__(self, instance: Instance) -> None:
        self.instance = instance

    async def _get_client(self, db_name: str | None = None):
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ImportError("pip install redis[hiredis]") from None
        password = decrypt_field(self.instance.password) or None
        db_index = int(db_name) if db_name and db_name.isdigit() else 0
        return aioredis.Redis(
            host=self.instance.host,
            port=self.instance.port or 6379,
            password=password,
            db=db_index,
            decode_responses=True,
            socket_connect_timeout=10,
        )

    async def test_connection(self) -> ResultSet:
        rs = ResultSet()
        try:
            r = await self._get_client()
            pong = await r.ping()
            rs.column_list = ["result"]
            rs.rows = [("PONG" if pong else "FAILED",)]
            await r.aclose()
        except Exception as e:
            rs.error = str(e)
        return rs

    def escape_string(self, value: str) -> str:
        return value

    async def get_all_databases(self) -> ResultSet:
        """Redis 固定返回 0-15 共 16 个数据库。"""
        rs = ResultSet()
        rs.column_list = ["db_index"]
        rs.rows = [(str(i),) for i in range(16)]
        return rs

    async def get_all_tables(self, db_name: str, **kw: Any) -> ResultSet:
        """Redis 无表概念，返回 KEY 类型分布。"""
        rs = ResultSet()
        try:
            r = await self._get_client(db_name)
            # 用 SCAN 采样前 100 个 key 统计类型分布
            type_count: dict[str, int] = {}
            async for key in r.scan_iter(count=100, match="*"):
                t = await r.type(key)
                type_count[t] = type_count.get(t, 0) + 1
                if sum(type_count.values()) >= 100:
                    break
            rs.column_list = ["type"]
            rs.rows = [(t,) for t in sorted(type_count.keys())]
            await r.aclose()
        except Exception as e:
            rs.error = str(e)
        return rs

    async def get_all_columns_by_tb(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet:
        rs = ResultSet()
        rs.column_list = ["info"]
        rs.rows = [("Redis 无列概念",)]
        return rs

    async def describe_table(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet:
        return await self.get_all_columns_by_tb(db_name, tb_name)

    async def get_tables_metas_data(self, db_name: str, **kw: Any) -> list:
        return []

    def query_check(self, db_name: str, sql: str) -> dict:
        cmd = sql.strip().split()[0].lower() if sql.strip() else ""
        if cmd not in ALLOWED_COMMANDS:
            return {
                "msg": f"在线查询不允许命令 {cmd.upper()}，允许的命令：{', '.join(sorted(ALLOWED_COMMANDS))}",
                "syntax_error": True,
            }
        return {"msg": "", "syntax_error": False}

    def filter_sql(self, sql: str, limit_num: int) -> str:
        return sql.strip()

    async def query(self, db_name: str, sql: str, limit_num: int = 0, parameters: dict | None = None, **kw: Any) -> ResultSet:
        rs = ResultSet()
        check = self.query_check(db_name, sql)
        if check["syntax_error"]:
            rs.error = check["msg"]
            return rs
        try:
            r = await self._get_client(db_name)
            parts = sql.strip().split()
            cmd = parts[0].lower()
            args = parts[1:]
            result = await r.execute_command(cmd, *args)
            await r.aclose()
            # 格式化结果
            if isinstance(result, (list, tuple)):
                rs.column_list = ["value"]
                if limit_num > 0:
                    result = result[:limit_num]
                rs.rows = [(str(v),) for v in result]
            elif isinstance(result, dict):
                rs.column_list = ["field", "value"]
                rs.rows = [(k, str(v)) for k, v in result.items()]
            else:
                rs.column_list = ["result"]
                rs.rows = [(str(result),)]
            rs.affected_rows = len(rs.rows)
        except Exception as e:
            rs.error = str(e)
        return rs

    def query_masking(self, db_name: str, sql: str, resultset: ResultSet) -> ResultSet:
        return resultset

    async def execute_check(self, db_name: str, sql: str) -> ReviewSet:
        review = ReviewSet(full_sql=sql)
        lines = [s.strip() for s in sql.strip().splitlines() if s.strip()]
        for i, line in enumerate(lines):
            cmd = line.split()[0].lower() if line.split() else ""
            item = SqlItem(id=i+1, sql=line)
            all_allowed = ALLOWED_COMMANDS | WORKFLOW_ALLOWED
            if cmd and cmd not in all_allowed:
                item.errlevel = 2
                item.errormessage = f"不允许的命令：{cmd.upper()}"
            review.rows.append(item)
        return review

    async def execute(self, db_name: str, sql: str, **kw: Any) -> ReviewSet:
        review = ReviewSet(full_sql=sql)
        try:
            r = await self._get_client(db_name)
            lines = [s.strip() for s in sql.strip().splitlines() if s.strip()]
            for i, line in enumerate(lines):
                parts = line.split()
                cmd = parts[0].lower() if parts else ""
                all_allowed = ALLOWED_COMMANDS | WORKFLOW_ALLOWED
                if cmd not in all_allowed:
                    review.rows.append(SqlItem(id=i+1, sql=line, errlevel=2,
                                               errormessage=f"不允许的命令：{cmd.upper()}"))
                    review.error = f"命令 {cmd} 不在允许列表"
                    break
                try:
                    result = await r.execute_command(cmd, *parts[1:])
                    review.rows.append(SqlItem(id=i+1, sql=line,
                                               stagestatus=f"OK: {result}"))
                except Exception as e:
                    review.rows.append(SqlItem(id=i+1, sql=line, errlevel=2, errormessage=str(e)))
                    review.error = str(e)
                    break
            await r.aclose()
        except Exception as e:
            review.error = str(e)
        return review

    async def execute_workflow(self, workflow: Any) -> ReviewSet:
        sql = workflow.content.sql_content if workflow.content else ""
        return await self.execute(workflow.db_name, sql)

    async def get_slow_log(self, db_name: str | None = None, limit: int = 50) -> ResultSet:
        rs = ResultSet()
        try:
            r = await self._get_client(db_name)
            logs = await r.slowlog_get(limit)
            rs.column_list = ["id", "start_time", "duration_us", "command"]
            rs.rows = [
                (log["id"], log["start_time"], log["duration"], " ".join(log["command"].decode().split()[:5]))
                for log in logs
            ]
            await r.aclose()
        except Exception as e:
            rs.error = str(e)
        return rs

    async def collect_slow_queries(
        self,
        since: Any | None = None,
        limit: int = 100,
        min_duration_ms: int = 1000,
    ) -> ResultSet:
        rs = await self.get_slow_log(limit=limit)
        if rs.is_success:
            rs.column_list = ["id", "duration_us", "command", "source", "source_ref"]
            rs.rows = [
                {
                    "id": row[0],
                    "duration_us": row[2],
                    "command": row[3],
                    "source": "redis_slowlog",
                    "source_ref": f"redis:{row[0]}",
                }
                for row in rs.rows
            ]
        return rs

    async def collect_metrics(self) -> dict:
        try:
            r = await self._get_client()
            info = await r.info("all")
            await r.aclose()
            return {
                "health": {"up": 1},
                "memory": {
                    "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
                    "used_memory_peak_mb": round(info.get("used_memory_peak", 0) / 1024 / 1024, 2),
                    "mem_fragmentation_ratio": info.get("mem_fragmentation_ratio", 0),
                },
                "stats": {
                    "connected_clients": info.get("connected_clients", 0),
                    "total_commands_processed": info.get("total_commands_processed", 0),
                    "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0),
                },
                "replication": {
                    "role": info.get("role", "unknown"),
                    "connected_slaves": info.get("connected_slaves", 0),
                },
            }
        except Exception as e:
            return {"health": {"up": 0}, "error": str(e)}

    def get_supported_metric_groups(self) -> list:
        return ["health", "memory", "stats", "replication"]
