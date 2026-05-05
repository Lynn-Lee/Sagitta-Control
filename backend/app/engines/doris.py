"""Apache Doris 引擎 - FE MySQL 协议连接，Doris 语义适配。"""

from __future__ import annotations

import re
from typing import Any

from app.engines.models import ResultSet, ReviewSet
from app.engines.mysql import MysqlEngine
from app.services.sql_audit import SqlAuditService


class DorisEngine(MysqlEngine):
    """Doris 数据库引擎。

    Doris FE 暴露 MySQL wire protocol，连接、参数化查询和大部分
    information_schema 元数据可复用 MySQL 引擎；这里补齐 Doris 自身的
    版本探测、只读查询边界、执行审核和基础监控。
    """

    name = "DorisEngine"
    db_type = "doris"

    async def test_connection(self) -> ResultSet:
        rs = await self.query(db_name="", sql="SELECT 1 AS ok", limit_num=1)
        if not rs.is_success:
            return rs
        version = await self._read_version()
        rs.column_list = ["result", "version"]
        rs.rows = [("ok", version)]
        rs.affected_rows = 1
        return rs

    async def _read_version(self) -> str:
        for sql in ("SELECT current_version() AS version", "SELECT VERSION() AS version"):
            rs = await self.query(db_name="", sql=sql, limit_num=1)
            if rs.is_success and rs.rows:
                return str(self._first_value(rs.rows[0]) or "")
        return ""

    @staticmethod
    def _first_value(row: Any) -> Any:
        if isinstance(row, dict):
            return next(iter(row.values()), None)
        if isinstance(row, (tuple, list)):
            return row[0] if row else None
        return row

    async def get_all_databases(self) -> ResultSet:
        rs = await super().get_all_databases()
        if rs.is_success:
            system_dbs = {"information_schema", "__internal_schema"}
            rs.rows = [
                row
                for row in rs.rows
                if str(self._first_value(row)).lower() not in system_dbs
            ]
            rs.affected_rows = len(rs.rows)
        return rs

    def filter_sql(self, sql: str, limit_num: int) -> str:
        if limit_num <= 0:
            return sql.strip().rstrip(";")
        sql_strip = sql.strip().rstrip(";")
        if sql_strip.lower().startswith(("select", "with")) and not re.search(
            r"\blimit\b", sql_strip, re.I
        ):
            return f"{sql_strip} LIMIT {limit_num}"
        return sql_strip

    async def execute_check(self, db_name: str, sql: str) -> ReviewSet:
        return SqlAuditService.audit(self.db_type, db_name, sql)

    async def execute(self, db_name: str, sql: str, **kwargs: Any) -> ReviewSet:
        review = await self.execute_check(db_name, sql)
        if review.error_count:
            return review
        return await super().execute(db_name=db_name, sql=sql, **kwargs)

    async def explain_query(self, db_name: str, sql: str) -> ResultSet:
        return await self.query(
            db_name=db_name,
            sql=f"EXPLAIN {sql.strip().rstrip(';')}",
            limit_num=1000,
        )

    async def collect_sql_activity(
        self,
        limit: int = 100,
        min_duration_ms: int = 1000,
    ) -> ResultSet:
        rs = await self.processlist(command_type="ALL")
        if not rs.is_success:
            return rs
        rows: list[dict[str, Any]] = []
        for row in rs.rows[: int(limit)]:
            if not isinstance(row, dict):
                continue
            sql_text = row.get("sql_text") or row.get("INFO") or row.get("Info")
            duration_ms = self._duration_ms_from_process_row(row)
            if not sql_text or duration_ms < min_duration_ms:
                continue
            rows.append(
                {
                    "source": "doris_queries",
                    "source_ref": f"doris:{row.get('session_id') or row.get('ID') or ''}",
                    "db_name": row.get("db_name") or row.get("DB") or "",
                    "sql_text": sql_text,
                    "duration_ms": duration_ms,
                    "username": row.get("username") or row.get("USER") or "",
                    "client_host": row.get("host") or row.get("HOST") or "",
                    "command": row.get("command") or row.get("COMMAND") or "",
                    "state": row.get("state") or row.get("STATE") or "",
                }
            )
        return ResultSet(
            column_list=[
                "source",
                "source_ref",
                "db_name",
                "sql_text",
                "duration_ms",
                "username",
                "client_host",
                "command",
                "state",
            ],
            rows=rows,
            affected_rows=len(rows),
        )

    async def collect_metrics(self) -> dict[str, Any]:
        health_rs = await self.query(db_name="", sql="SELECT 1 AS ok", limit_num=1)
        version = await self._read_version() if health_rs.is_success else ""
        process_rs = await self.processlist(command_type="ALL") if health_rs.is_success else ResultSet()
        return {
            "health": {"up": 1 if health_rs.is_success else 0, "error": health_rs.error},
            "version": {"value": version},
            "queries": {
                "current": len(process_rs.rows) if process_rs.is_success else None,
                "warning": process_rs.error if process_rs.error else "",
            },
        }

    def get_supported_metric_groups(self) -> list[str]:
        return ["health", "queries", "version"]

    @staticmethod
    def _duration_ms_from_process_row(row: dict[str, Any]) -> int:
        raw_ms = row.get("duration_ms")
        if raw_ms is not None:
            return int(float(raw_ms or 0))
        raw_seconds = row.get("time_seconds", row.get("TIME", row.get("Time", 0)))
        return int(float(raw_seconds or 0) * 1000)
