"""StarRocks 引擎（3.x/4.x）- FE MySQL 协议连接，StarRocks 语义适配。"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import sqlglot
import sqlglot.expressions as exp

from app.engines.models import ResultSet, ReviewSet, SqlItem
from app.engines.mysql import MysqlEngine
from app.engines.utils import sanitize_sqlglot_error

logger = logging.getLogger(__name__)


_PRIVILEGE_ERROR_MARKERS = (
    "access denied",
    "denied",
    "privilege",
    "permission",
    "not authorized",
    "unauthorized",
    "system-level operate",
    "cluster_admin",
    "errcode = 2",
)

_READ_PREFIXES = (
    "select",
    "with",
    "show",
    "desc",
    "describe",
    "explain",
)

_VARIABLE_WRITE_ALLOWLIST = {
    "query_timeout",
    "insert_timeout",
    "exec_mem_limit",
    "parallel_fragment_exec_instance_num",
    "enable_profile",
}


@dataclass
class StarRocksCapabilities:
    basic_rw: bool = False
    process_read: bool = False
    session_kill: bool = False
    cluster_inspect: bool = False
    variable_write: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "basic_rw": self.basic_rw,
            "process_read": self.process_read,
            "session_kill": self.session_kill,
            "cluster_inspect": self.cluster_inspect,
            "variable_write": self.variable_write,
        }


class StarRocksEngine(MysqlEngine):
    """StarRocks 数据库引擎。

    StarRocks 使用 MySQL wire protocol 对外连接，但 SQL 能力、元数据、
    集群诊断和 DELETE 约束均按 StarRocks 自身语义处理。
    """

    name = "StarRocksEngine"
    db_type = "starrocks"

    def __init__(self, instance: Any) -> None:
        super().__init__(instance)
        self._capabilities: StarRocksCapabilities | None = None
        self._server_version: tuple[int, ...] = ()

    # ── 连接与能力探测 ───────────────────────────────────────

    async def test_connection(self) -> ResultSet:
        rs = ResultSet()
        start_rs = await self.query(db_name="", sql="SELECT 1 AS ok", limit_num=1)
        rs.cost_time = start_rs.cost_time
        if start_rs.error:
            rs.error = start_rs.error
            return rs

        version = await self._read_version()
        capabilities = await self.probe_capabilities(force=True)
        rs.column_list = ["result", "version", "capabilities"]
        rs.rows = [("ok", version, capabilities.to_dict())]
        rs.warning = self._capability_warning(capabilities)
        return rs

    @property
    def server_version(self) -> tuple[int, ...]:
        return self._server_version

    async def _read_version(self) -> str:
        for sql in ("SELECT current_version() AS version", "SELECT VERSION() AS version"):
            rs = await self.query(db_name="", sql=sql, limit_num=1)
            if rs.is_success and rs.rows:
                value = self._first_value(rs.rows[0])
                version = str(value or "")
                self._server_version = tuple(int(x) for x in re.findall(r"\d+", version)[:3])
                return version
        return ""

    async def probe_capabilities(self, force: bool = False) -> StarRocksCapabilities:
        if self._capabilities is not None and not force:
            return self._capabilities

        caps = StarRocksCapabilities()
        caps.basic_rw = (await self._safe_query("SELECT 1 AS ok")).is_success
        caps.process_read = (await self._safe_query("SHOW PROCESSLIST")).is_success

        frontend_rs = await self._safe_query("SHOW FRONTENDS")
        backend_rs = await self._safe_query("SHOW PROC '/backends'")
        caps.cluster_inspect = frontend_rs.is_success or backend_rs.is_success

        grants_rs = await self._safe_query("SHOW GRANTS")
        if grants_rs.is_success:
            grants_text = " ".join(str(row).upper() for row in grants_rs.rows)
            caps.session_kill = (
                "CLUSTER_ADMIN" in grants_text
                or "NODE" in grants_text
                or "OPERATE" in grants_text
                or "ALL" in grants_text
            )
            caps.variable_write = (
                "ADMIN" in grants_text
                or "CLUSTER_ADMIN" in grants_text
                or "ALL" in grants_text
            )
        else:
            caps.session_kill = caps.cluster_inspect
            caps.variable_write = False

        self._capabilities = caps
        return caps

    async def _safe_query(self, sql: str, db_name: str = "") -> ResultSet:
        try:
            return await self.query(db_name=db_name, sql=sql, limit_num=0)
        except Exception as e:
            return ResultSet(error=str(e))

    @staticmethod
    def _is_privilege_error(error: str) -> bool:
        lower = error.lower()
        return any(marker in lower for marker in _PRIVILEGE_ERROR_MARKERS)

    @staticmethod
    def _capability_warning(caps: StarRocksCapabilities) -> str:
        if caps.cluster_inspect and caps.session_kill:
            return ""
        return "当前 StarRocks 账号缺少部分管理权限，集群诊断/Kill/变量写入能力将按权限降级"

    @staticmethod
    def _first_value(row: Any) -> Any:
        if isinstance(row, dict):
            return next(iter(row.values()), None)
        if isinstance(row, (tuple, list)):
            return row[0] if row else None
        return row

    # ── 元数据 ───────────────────────────────────────────────

    async def get_all_databases(self) -> ResultSet:
        rs = await self.query(db_name="", sql="SHOW DATABASES", limit_num=0)
        if rs.is_success and self.instance.show_db_name_regex:
            pattern = re.compile(self.instance.show_db_name_regex)
            rs.rows = [r for r in rs.rows if pattern.search(str(self._first_value(r)))]
        return rs

    async def get_all_tables(self, db_name: str, **kwargs: Any) -> ResultSet:
        db_safe = self.escape_string(db_name)
        return await self.query(db_name=db_name, sql=f"SHOW TABLES FROM `{db_safe}`", limit_num=0)

    async def get_all_columns_by_tb(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        sql = (
            "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, "
            "COLUMN_COMMENT, COLUMN_KEY, EXTRA "
            "FROM information_schema.columns "
            "WHERE TABLE_SCHEMA = %(db)s AND TABLE_NAME = %(tb)s "
            "ORDER BY ORDINAL_POSITION"
        )
        return await self.query(
            db_name=db_name,
            sql=sql,
            parameters={"db": db_name, "tb": tb_name},
            limit_num=0,
        )

    async def describe_table(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        db_safe = self.escape_string(db_name)
        tb_safe = self.escape_string(tb_name)
        return await self.query(
            db_name=db_name,
            sql=f"SHOW CREATE TABLE `{db_safe}`.`{tb_safe}`",
            limit_num=0,
        )

    async def get_tables_metas_data(
        self, db_name: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT TABLE_NAME, TABLE_COMMENT, TABLE_ROWS, DATA_LENGTH, "
            "CREATE_TIME, UPDATE_TIME, ENGINE, TABLE_TYPE "
            "FROM information_schema.tables "
            "WHERE TABLE_SCHEMA = %(db)s "
            "ORDER BY TABLE_NAME"
        )
        rs = await self.query(db_name=db_name, sql=sql, parameters={"db": db_name}, limit_num=0)
        if not rs.is_success:
            return []
        return [
            row if isinstance(row, dict) else dict(zip(rs.column_list, row, strict=False))
            for row in rs.rows
        ]

    async def get_table_constraints(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        sql = (
            "SELECT COLUMN_KEY AS constraint_type, COLUMN_NAME AS column_names "
            "FROM information_schema.columns "
            "WHERE TABLE_SCHEMA = %(db)s AND TABLE_NAME = %(tb)s AND COALESCE(COLUMN_KEY, '') != '' "
            "ORDER BY ORDINAL_POSITION"
        )
        rs = await self.query(
            db_name=db_name,
            sql=sql,
            parameters={"db": db_name, "tb": tb_name},
            limit_num=0,
        )
        if rs.is_success:
            rs.warning = "StarRocks 仅返回信息模式可见的键约束信息"
        return rs

    async def get_table_indexes(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        rs = await self.get_table_constraints(db_name, tb_name, **kwargs)
        if rs.is_success:
            rs.warning = "StarRocks 不提供 MySQL STATISTICS 等价索引视图，当前返回键列信息"
        return rs

    # ── 查询与审核 ───────────────────────────────────────────

    def query_check(self, db_name: str, sql: str) -> dict[str, Any]:
        result: dict[str, Any] = {"msg": "", "has_star": False, "syntax_error": False}
        sql_strip = sql.strip().rstrip(";")
        if not sql_strip:
            result["syntax_error"] = True
            result["msg"] = "SQL 不能为空"
            return result

        prefix = sql_strip.split(None, 1)[0].lower()
        if prefix not in _READ_PREFIXES:
            result["msg"] = f"查询接口不允许执行 {prefix.upper()} 操作"
            return result

        if prefix in {"show", "desc", "describe"}:
            return result

        try:
            tree = sqlglot.parse_one(sql_strip, dialect="mysql")
        except sqlglot.errors.ParseError as e:
            if prefix == "explain":
                return result
            result["syntax_error"] = True
            result["msg"] = f"SQL 语法错误：{sanitize_sqlglot_error(str(e))}"
            return result

        for _ in tree.find_all(exp.Star):
            result["has_star"] = True
            break

        write_types = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.TruncateTable)
        found_write = next((tree.find(wt) for wt in write_types if tree.find(wt)), None)
        if found_write is not None:
            result["msg"] = f"查询接口不允许执行写操作：{type(found_write).__name__}"
        return result

    def filter_sql(self, sql: str, limit_num: int) -> str:
        if limit_num <= 0:
            return sql
        sql_strip = sql.strip().rstrip(";")
        sql_lower = sql_strip.lower()
        if sql_lower.startswith(("select", "with")) and not re.search(r"\blimit\b", sql_lower):
            return f"{sql_strip} LIMIT {limit_num}"
        return sql_strip

    async def execute_check(self, db_name: str, sql: str) -> ReviewSet:
        review = ReviewSet(full_sql=sql)
        try:
            statements = sqlglot.parse(sql, dialect="mysql")
        except Exception as e:
            review.append(SqlItem(id=1, sql=sql, errlevel=2, errormessage=f"SQL 解析失败：{e}"))
            return review

        for idx, stmt in enumerate(statements):
            item = SqlItem(id=idx + 1, sql=str(stmt) if stmt is not None else "")
            if stmt is None:
                item.errlevel = 2
                item.errormessage = "无法解析的 SQL 语句"
                review.append(item)
                continue

            if isinstance(stmt, (exp.Drop, exp.TruncateTable, exp.Alter)):
                item.errlevel = 1
                item.errormessage = f"StarRocks 高风险 DDL：{type(stmt).__name__}，请确认已备份或可回滚"

            if isinstance(stmt, (exp.Update, exp.Delete)) and not stmt.find(exp.Where):
                item.errlevel = 2
                item.errormessage = "StarRocks UPDATE/DELETE 必须包含 WHERE 条件"

            if isinstance(stmt, exp.Delete) and re.search(r"\blimit\b", item.sql, re.I):
                item.errlevel = 2
                item.errormessage = "StarRocks DELETE 不按 MySQL DELETE ... LIMIT 分批执行，请使用明确 WHERE 条件"

            if isinstance(stmt, exp.Select):
                for _ in stmt.find_all(exp.Star):
                    item.errlevel = max(item.errlevel, 1)
                    item.errormessage = "建议避免使用 SELECT *，明确指定列名"
                    break

            item.stagestatus = "Audit completed" if not item.errlevel else "Audit warning/error"
            review.append(item)
        return review

    async def execute(self, db_name: str, sql: str, **kwargs: Any) -> ReviewSet:
        review = await self.execute_check(db_name, sql)
        if review.error_count:
            return review
        return await super().execute(db_name=db_name, sql=sql, **kwargs)

    # ── 诊断、变量、监控 ─────────────────────────────────────

    async def processlist(
        self, command_type: str = "Query", **kwargs: Any
    ) -> ResultSet:
        rs = await self.query(db_name="", sql="SHOW PROCESSLIST", limit_num=0)
        if not rs.is_success:
            if self._is_privilege_error(rs.error):
                rs.error = "当前 StarRocks 账号缺少查看会话权限"
            return rs
        if command_type and command_type != "ALL" and rs.rows:
            rs.rows = [
                row for row in rs.rows
                if str(self._row_get(row, "Command", "COMMAND", "command")).lower()
                == command_type.lower()
            ]
        return rs

    async def kill_connection(self, thread_id: int) -> ResultSet:
        rs = await self.query(db_name="", sql=f"KILL {int(thread_id)}", limit_num=0)
        if rs.error and self._is_privilege_error(rs.error):
            rs.error = "当前 StarRocks 账号缺少 Kill 会话权限，需要特权管理账号"
        elif rs.is_success and self._capabilities:
            self._capabilities.session_kill = True
        return rs

    async def get_variables(
        self, variables: list[str] | None = None
    ) -> ResultSet:
        if variables:
            placeholders = ", ".join(f"%(v{i})s" for i in range(len(variables)))
            params = {f"v{i}": v for i, v in enumerate(variables)}
            sql = f"SHOW VARIABLES WHERE Variable_name IN ({placeholders})"
            return await self.query(db_name="", sql=sql, parameters=params, limit_num=0)
        return await self.query(db_name="", sql="SHOW VARIABLES", limit_num=0)

    async def set_variable(
        self, variable_name: str, variable_value: str
    ) -> ResultSet:
        name = variable_name.strip().lower()
        if name not in _VARIABLE_WRITE_ALLOWLIST:
            return ResultSet(error=f"StarRocks 参数 {variable_name} 不在允许修改列表中")
        safe_name = self.escape_string(name)
        safe_value = str(variable_value).replace("'", "''")
        rs = await self.query(db_name="", sql=f"SET {safe_name} = '{safe_value}'", limit_num=0)
        if rs.error and self._is_privilege_error(rs.error):
            rs.error = "当前 StarRocks 账号缺少参数写入权限，需要特权管理账号"
        return rs

    async def collect_metrics(self) -> dict[str, Any]:
        health_rs = await self.query(db_name="", sql="SELECT 1 AS ok", limit_num=1)
        version = await self._read_version() if health_rs.is_success else ""
        metrics: dict[str, Any] = {
            "health": {"up": 1 if health_rs.is_success else 0, "error": health_rs.error},
            "version": {"value": version},
        }

        proc_rs = await self.processlist(command_type="ALL")
        if proc_rs.is_success:
            metrics["queries"] = {"current": len(proc_rs.rows)}
        else:
            metrics["queries"] = {"warning": proc_rs.error}

        cluster: dict[str, Any] = {}
        fe_rs = await self._safe_query("SHOW FRONTENDS")
        be_rs = await self._safe_query("SHOW PROC '/backends'")
        cn_rs = await self._safe_query("SHOW PROC '/compute_nodes'")
        for key, rs in (("frontends", fe_rs), ("backends", be_rs), ("compute_nodes", cn_rs)):
            if rs.is_success:
                cluster[key] = {"count": len(rs.rows), "rows": rs.rows}
            elif self._is_privilege_error(rs.error):
                cluster[key] = {"warning": "当前 StarRocks 账号缺少 SYSTEM OPERATE/cluster_admin，已跳过集群节点指标"}
            elif rs.error:
                cluster[key] = {"warning": rs.error}
        metrics["cluster"] = cluster
        return metrics

    def get_supported_metric_groups(self) -> list[str]:
        return ["health", "queries", "cluster", "frontends", "backends", "compute_nodes"]

    @staticmethod
    def _row_get(row: Any, *names: str) -> Any:
        if isinstance(row, dict):
            lowered = {str(k).lower(): v for k, v in row.items()}
            for name in names:
                if name.lower() in lowered:
                    return lowered[name.lower()]
            return ""
        return ""
