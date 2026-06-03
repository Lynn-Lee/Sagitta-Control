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

    async def get_table_constraints(self, db_name: str, tb_name: str, **kwargs: Any) -> ResultSet:
        rs = await self.get_all_columns_by_tb(db_name, tb_name, **kwargs)
        if not rs.is_success:
            return rs
        rows = self._rows_to_dicts(rs)
        key_columns: dict[str, list[str]] = {}
        for row in rows:
            key = str(self._row_get(row, "COLUMN_KEY", "column_key") or "").upper()
            column = str(self._row_get(row, "COLUMN_NAME", "column_name") or "")
            if not key or not column:
                continue
            if key == "PRI":
                key_columns.setdefault("PRIMARY KEY", []).append(column)
            elif key == "UNI":
                key_columns.setdefault("UNIQUE", []).append(column)
        result_rows = [
            {
                "constraint_name": "PRIMARY" if constraint_type == "PRIMARY KEY" else constraint_type,
                "constraint_type": constraint_type,
                "column_names": ", ".join(columns),
                "referenced_table_name": "",
                "referenced_column_names": "",
                "check_clause": "",
            }
            for constraint_type, columns in key_columns.items()
        ]
        return ResultSet(
            column_list=[
                "constraint_name",
                "constraint_type",
                "column_names",
                "referenced_table_name",
                "referenced_column_names",
                "check_clause",
            ],
            rows=result_rows,
            affected_rows=len(result_rows),
            warning="Doris 不提供完整关系型约束目录，已按列 KEY 元数据降级展示",
        )

    async def get_table_indexes(self, db_name: str, tb_name: str, **kwargs: Any) -> ResultSet:
        rs = await self.get_table_constraints(db_name, tb_name, **kwargs)
        if not rs.is_success:
            return rs
        rows: list[dict[str, Any]] = []
        for row in self._rows_to_dicts(rs):
            constraint_type = str(row.get("constraint_type") or "")
            columns = str(row.get("column_names") or "")
            if not columns:
                continue
            rows.append(
                {
                    "index_name": row.get("constraint_name") or constraint_type,
                    "index_type": "PRIMARY KEY INDEX"
                    if constraint_type == "PRIMARY KEY"
                    else "UNIQUE INDEX",
                    "column_names": columns,
                    "is_composite": "YES" if "," in columns else "NO",
                    "index_comment": "",
                }
            )
        return ResultSet(
            column_list=[
                "index_name",
                "index_type",
                "column_names",
                "is_composite",
                "index_comment",
            ],
            rows=rows,
            affected_rows=len(rows),
            warning=rs.warning,
        )

    async def processlist(self, command_type: str = "ALL", **kwargs: Any) -> ResultSet:
        rs = await self.query(db_name="", sql="SHOW PROCESSLIST", limit_num=0)
        if not rs.is_success:
            return rs
        normalized_rows: list[dict[str, Any]] = []
        for row in self._rows_to_dicts(rs):
            command = self._row_get(row, "COMMAND", "Command", "command")
            if command_type and command_type != "ALL" and str(command) != command_type:
                continue
            time_seconds = self._row_get(row, "TIME", "Time", "time_seconds") or 0
            try:
                duration_ms = int(float(time_seconds) * 1000)
            except (TypeError, ValueError):
                duration_ms = 0
            normalized_rows.append(
                {
                    "session_id": self._row_get(row, "ID", "Id", "session_id"),
                    "username": self._row_get(row, "USER", "User", "username"),
                    "host": self._row_get(row, "HOST", "Host", "host"),
                    "db_name": self._row_get(row, "DB", "Db", "db_name"),
                    "command": command,
                    "time_seconds": time_seconds,
                    "state_duration_ms": duration_ms,
                    "duration_ms": duration_ms,
                    "duration_source": "show_processlist",
                    "state": self._row_get(row, "STATE", "State", "state"),
                    "sql_text": self._row_get(row, "INFO", "Info", "sql_text"),
                }
            )
        return ResultSet(
            column_list=[
                "session_id",
                "username",
                "host",
                "db_name",
                "command",
                "time_seconds",
                "state_duration_ms",
                "duration_ms",
                "duration_source",
                "state",
                "sql_text",
            ],
            rows=normalized_rows,
            affected_rows=len(normalized_rows),
        )

    async def collect_sql_activity(
        self,
        limit: int = 100,
        min_duration_ms: int = 1000,
        window_minutes: int = 30,
        start_time: Any | None = None,
        end_time: Any | None = None,
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
        missing_groups: dict[str, str] = {}
        metrics: dict[str, Any] = {
            "health": {"up": 1 if health_rs.is_success else 0, "error": health_rs.error},
            "version": {"value": version},
            "queries": {
                "current": len(process_rs.rows) if process_rs.is_success else None,
                "warning": process_rs.error if process_rs.error else "",
            },
        }
        fe_rs = await self._safe_query("SHOW FRONTENDS")
        be_rs = await self._safe_query("SHOW BACKENDS")
        load_rs = await self._safe_query("SHOW LOAD LIMIT 20")
        routine_load_rs = await self._safe_query("SHOW ROUTINE LOAD")
        compaction_rs = await self._safe_query("SHOW PROC '/compactions'")
        tablet_rs = await self._safe_query("SHOW PROC '/statistic'")
        metrics["cluster"] = {
            "frontends": self._summarize_rows(
                fe_rs, missing_groups=missing_groups, group_name="doris_frontends"
            ),
            "backends": self._summarize_rows(
                be_rs, missing_groups=missing_groups, group_name="doris_backends"
            ),
        }
        metrics["load_jobs"] = self._summarize_state_rows(
            load_rs,
            state_fields=("State", "STATE", "JobState"),
            missing_groups=missing_groups,
            group_name="doris_load_jobs",
        )
        metrics["routine_load_jobs"] = self._summarize_state_rows(
            routine_load_rs,
            state_fields=("State", "STATE"),
            missing_groups=missing_groups,
            group_name="doris_routine_load_jobs",
        )
        metrics["compactions"] = self._summarize_rows(
            compaction_rs, missing_groups=missing_groups, group_name="doris_compactions"
        )
        metrics["tablets"] = self._summarize_rows(
            tablet_rs, missing_groups=missing_groups, group_name="doris_tablets"
        )
        if missing_groups:
            metrics["missing_groups"] = missing_groups
        return metrics

    def get_supported_metric_groups(self) -> list[str]:
        return [
            "health",
            "queries",
            "version",
            "cluster",
            "load_jobs",
            "routine_load_jobs",
            "compactions",
            "tablets",
        ]

    async def _safe_query(self, sql: str, db_name: str = "") -> ResultSet:
        try:
            return await self.query(db_name=db_name, sql=sql, limit_num=0)
        except Exception as exc:
            return ResultSet(error=str(exc))

    @staticmethod
    def _rows_to_dicts(rs: ResultSet) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in rs.rows:
            if isinstance(row, dict):
                rows.append({str(k): v for k, v in row.items()})
            elif rs.column_list:
                rows.append(dict(zip(rs.column_list, row, strict=False)))
            else:
                rows.append({"value": row})
        return rows

    @classmethod
    def _summarize_rows(
        cls,
        rs: ResultSet,
        *,
        missing_groups: dict[str, str],
        group_name: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        if not rs.is_success:
            if rs.error:
                missing_groups[group_name] = rs.error
            return {"count": None, "rows": [], "warning": rs.error}
        rows = cls._rows_to_dicts(rs)
        return {"count": len(rows), "rows": rows[:limit]}

    @classmethod
    def _summarize_state_rows(
        cls,
        rs: ResultSet,
        *,
        state_fields: tuple[str, ...],
        missing_groups: dict[str, str],
        group_name: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        summary = cls._summarize_rows(
            rs, missing_groups=missing_groups, group_name=group_name, limit=limit
        )
        counts: dict[str, int] = {}
        for row in summary.get("rows") or []:
            state = str(cls._row_get(row, *state_fields) or "UNKNOWN")
            counts[state] = counts.get(state, 0) + 1
        summary["state_counts"] = counts
        return summary

    @staticmethod
    def _row_get(row: dict[str, Any], *names: str) -> Any:
        lowered = {str(k).lower(): v for k, v in row.items()}
        for name in names:
            if name.lower() in lowered:
                return lowered[name.lower()]
        return ""

    @staticmethod
    def _duration_ms_from_process_row(row: dict[str, Any]) -> int:
        raw_ms = row.get("duration_ms")
        if raw_ms is not None:
            return int(float(raw_ms or 0))
        raw_seconds = row.get("time_seconds", row.get("TIME", row.get("Time", 0)))
        return int(float(raw_seconds or 0) * 1000)
