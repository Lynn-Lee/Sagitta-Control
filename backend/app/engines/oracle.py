"""
Oracle 引擎最小可用实现。

当前首要目标：
- 测试连接
- 同步 Schema 列表
- 获取指定 Schema 下的表 / 列

实例配置中的 db_name 对 Oracle 语义为 Service Name / PDB。
"""

from __future__ import annotations

import asyncio
import logging
import platform
import re
import time
import uuid
from threading import Lock
from typing import TYPE_CHECKING, Any

import oracledb
import sqlglot
import sqlglot.expressions as exp

from app.core.config import settings
from app.core.security import decrypt_field
from app.engines.models import ResultSet, ReviewSet, SqlItem
from app.engines.utils import normalize_engine_host, sanitize_sqlglot_error

if TYPE_CHECKING:
    from app.models.instance import Instance

logger = logging.getLogger(__name__)
_ORACLE_CLIENT_INIT_LOCK = Lock()
_ORACLE_CLIENT_INIT_ATTEMPTED = False
_ORACLE_CLIENT_INIT_ERROR: str | None = None
_RAW_DDL_TRANSFORM_SQL = """
BEGIN
    DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', true);
    DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'PRETTY', true);
END;
"""


def _build_thick_mode_error(exc: Exception) -> str:
    return (
        "Oracle Thick 模式初始化失败。"
        "当前实例需要 Oracle Instant Client 才能连接低版本数据库；"
        "请确认容器或宿主机已安装 Instant Client，并将 ORACLE_DRIVER_MODE=thick。"
        f"原始错误: {exc}"
    )


def _init_oracle_client_if_needed() -> None:
    global _ORACLE_CLIENT_INIT_ATTEMPTED, _ORACLE_CLIENT_INIT_ERROR

    mode = settings.ORACLE_DRIVER_MODE.strip().lower()
    if mode == "thin":
        return

    with _ORACLE_CLIENT_INIT_LOCK:
        if _ORACLE_CLIENT_INIT_ATTEMPTED:
            if _ORACLE_CLIENT_INIT_ERROR and mode == "thick":
                raise RuntimeError(_ORACLE_CLIENT_INIT_ERROR)
            return

        _ORACLE_CLIENT_INIT_ATTEMPTED = True
        kwargs: dict[str, str] = {}
        config_dir = settings.ORACLE_CLIENT_CONFIG_DIR.strip()
        lib_dir = settings.ORACLE_CLIENT_LIB_DIR.strip()

        if config_dir:
            kwargs["config_dir"] = config_dir

        if lib_dir:
            if platform.system().lower() == "linux":
                logger.info(
                    "oracle_client_lib_dir_ignored_on_linux lib_dir=%s",
                    lib_dir,
                )
            else:
                kwargs["lib_dir"] = lib_dir

        try:
            oracledb.init_oracle_client(**kwargs)
            logger.info(
                "oracle_client_initialized mode=thick config_dir=%s",
                config_dir or "(default)",
            )
        except Exception as exc:
            _ORACLE_CLIENT_INIT_ERROR = _build_thick_mode_error(exc)
            if mode == "thick":
                raise RuntimeError(_ORACLE_CLIENT_INIT_ERROR) from exc
            logger.warning(
                "oracle_client_init_failed_fallback_to_thin error=%s",
                _ORACLE_CLIENT_INIT_ERROR,
            )


def _normalize_oracle_connect_error(exc: Exception) -> str:
    message = str(exc)
    if "DPY-3010" in message:
        return (
            f"{message}；当前 SagittaDB 正在使用 python-oracledb Thin 模式。"
            "Oracle 11.2 及更早版本需安装 Instant Client，并将 ORACLE_DRIVER_MODE=thick。"
        )
    return message


class OracleEngine:
    name = "OracleEngine"
    db_type = "oracle"

    def __init__(self, instance: Instance) -> None:
        self.instance = instance
        self._host = normalize_engine_host(instance.host)
        self._port = instance.port
        self._user = decrypt_field(instance.user)
        self._password = decrypt_field(instance.password)
        self._service_name = instance.db_name or "FREEPDB1"

    def _dsn(self) -> str:
        return f"{self._host}:{self._port}/{self._service_name}"

    def _connect_sync(self):
        _init_oracle_client_if_needed()
        return oracledb.connect(
            user=self._user,
            password=self._password,
            dsn=self._dsn(),
        )

    def _run_query_sync(self, sql: str, params: dict[str, Any] | None = None) -> ResultSet:
        rs = ResultSet()
        start = time.monotonic()
        conn = None
        try:
            conn = self._connect_sync()
            with conn.cursor() as cur:
                cur.execute(sql, params or {})
                if cur.description:
                    rs.column_list = [col[0] for col in cur.description]
                    rs.rows = cur.fetchall()
                    rs.affected_rows = len(rs.rows)
                else:
                    rs.affected_rows = cur.rowcount or 0
        except Exception as e:
            rs.error = _normalize_oracle_connect_error(e)
            logger.warning("oracle_query_error: %s", rs.error)
        finally:
            if conn is not None:
                conn.close()
            rs.cost_time = int((time.monotonic() - start) * 1000)
        return rs

    def _run_statement_sync(self, sql: str, params: dict[str, Any] | None = None) -> ResultSet:
        rs = ResultSet()
        start = time.monotonic()
        conn = None
        try:
            conn = self._connect_sync()
            with conn.cursor() as cur:
                cur.execute(sql, params or {})
                rs.affected_rows = cur.rowcount or 0
            conn.commit()
        except Exception as e:
            rs.error = _normalize_oracle_connect_error(e)
            logger.warning("oracle_statement_error: %s", rs.error)
        finally:
            if conn is not None:
                conn.close()
            rs.cost_time = int((time.monotonic() - start) * 1000)
        return rs

    async def get_connection(self, db_name: str | None = None):
        return await asyncio.to_thread(self._connect_sync)

    async def test_connection(self) -> ResultSet:
        return await asyncio.to_thread(self._run_query_sync, "SELECT 1 FROM dual", None)

    def escape_string(self, value: str) -> str:
        return value.replace('"', '""')

    async def get_all_databases(self) -> ResultSet:
        primary_sql = """
        SELECT username
        FROM dba_users
        ORDER BY username
        """
        rs = await asyncio.to_thread(self._run_query_sync, primary_sql, None)
        if rs.is_success:
            return rs

        logger.info("oracle_fallback_visible_schemas: %s", rs.error)
        fallback_sql = """
        SELECT username
        FROM user_users
        ORDER BY username
        """
        return await asyncio.to_thread(self._run_query_sync, fallback_sql, None)

    async def get_all_tables(self, db_name: str, **kwargs: Any) -> ResultSet:
        sql = """
        SELECT table_name
        FROM all_tables
        WHERE owner = :owner
        ORDER BY table_name
        """
        return await asyncio.to_thread(self._run_query_sync, sql, {"owner": db_name.upper()})

    async def get_all_columns_by_tb(self, db_name: str, tb_name: str, **kwargs: Any) -> ResultSet:
        sql = """
        SELECT c.column_name,
               c.data_type,
               c.nullable,
               c.data_default,
               COALESCE(cm.comments, '') AS column_comment
        FROM all_tab_columns c
        LEFT JOIN all_col_comments cm
          ON c.owner = cm.owner
         AND c.table_name = cm.table_name
         AND c.column_name = cm.column_name
        WHERE c.owner = :owner AND c.table_name = :table_name
        ORDER BY c.column_id
        """
        return await asyncio.to_thread(
            self._run_query_sync,
            sql,
            {"owner": db_name.upper(), "table_name": tb_name.upper()},
        )

    async def describe_table(self, db_name: str, tb_name: str, **kwargs: Any) -> ResultSet:
        rs = await asyncio.to_thread(self._get_table_ddl_sync, db_name, tb_name)
        if rs.is_success and rs.rows:
            return rs
        return await self.get_all_columns_by_tb(db_name, tb_name, **kwargs)

    async def explain_query(self, db_name: str, sql: str) -> ResultSet:
        statement_id = f"SAGITTA_{uuid.uuid4().hex[:24].upper()}"
        explain_sql = f"EXPLAIN PLAN SET STATEMENT_ID = '{statement_id}' FOR {sql.strip().rstrip(';')}"
        rs = await asyncio.to_thread(self._run_statement_sync, explain_sql, None)
        if not rs.is_success:
            return rs
        display_sql = """
        SELECT plan_table_output
        FROM TABLE(DBMS_XPLAN.DISPLAY(NULL, :statement_id, 'TYPICAL +PREDICATE +ALIAS +COST +BYTES'))
        """
        plan_rs = await asyncio.to_thread(self._run_query_sync, display_sql, {"statement_id": statement_id})
        cleanup_sql = "DELETE FROM plan_table WHERE statement_id = :statement_id"
        await asyncio.to_thread(self._run_statement_sync, cleanup_sql, {"statement_id": statement_id})
        return plan_rs

    def _normalize_ddl_text(self, ddl: str) -> str:
        normalized = ddl.replace("\r\n", "\n").replace("\r", "\n").strip()
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized

    def _get_table_ddl_sync(self, db_name: str, tb_name: str) -> ResultSet:
        rs = ResultSet()
        start = time.monotonic()
        conn = None
        try:
            conn = self._connect_sync()
            with conn.cursor() as cur:
                try:
                    cur.execute(_RAW_DDL_TRANSFORM_SQL)
                except Exception as exc:
                    logger.info("oracle_set_metadata_transform_failed: %s", exc)
                cur.execute(
                    """
                    SELECT DBMS_METADATA.GET_DDL('TABLE', :table_name, :owner) AS create_table
                    FROM dual
                    """,
                    {"table_name": tb_name.upper(), "owner": db_name.upper()},
                )
                row = cur.fetchone()
                ddl = row[0] if row else None
                if ddl is None:
                    rs.error = "未获取到表 DDL"
                else:
                    ddl_text = ddl.read() if hasattr(ddl, "read") else str(ddl)
                    rs.column_list = ["CREATE TABLE"]
                    rs.rows = [(self._normalize_ddl_text(ddl_text),)]
                    rs.affected_rows = 1
        except Exception as exc:
            rs.error = _normalize_oracle_connect_error(exc)
            logger.info("oracle_get_table_ddl_failed: %s", rs.error)
        finally:
            if conn is not None:
                conn.close()
            rs.cost_time = int((time.monotonic() - start) * 1000)
        return rs

    async def get_tables_metas_data(self, db_name: str, **kwargs: Any) -> list[dict[str, Any]]:
        rs = await self.get_all_tables(db_name)
        if not rs.is_success:
            return []
        return [{"table_name": row[0]} for row in rs.rows]

    async def get_table_constraints(self, db_name: str, tb_name: str, **kwargs: Any) -> ResultSet:
        sql = """
        SELECT
            c.constraint_name,
            CASE c.constraint_type
              WHEN 'P' THEN 'PRIMARY KEY'
              WHEN 'U' THEN 'UNIQUE'
              WHEN 'R' THEN 'FOREIGN KEY'
              WHEN 'C' THEN 'CHECK'
              ELSE c.constraint_type
            END AS constraint_type,
            LISTAGG(cols.column_name, ', ') WITHIN GROUP (ORDER BY cols.position) AS column_names,
            MAX(ref.table_name) AS referenced_table_name,
            LISTAGG(ref_cols.column_name, ', ') WITHIN GROUP (ORDER BY ref_cols.position) AS referenced_column_names,
            MAX(CASE WHEN c.constraint_type = 'C' THEN c.search_condition_vc ELSE '' END) AS check_clause
            /* '' AS check_clause */
        FROM all_constraints c
        JOIN all_cons_columns cols
          ON c.owner = cols.owner
         AND c.constraint_name = cols.constraint_name
        LEFT JOIN all_constraints ref
          ON c.r_owner = ref.owner
         AND c.r_constraint_name = ref.constraint_name
        LEFT JOIN all_cons_columns ref_cols
          ON ref.owner = ref_cols.owner
         AND ref.constraint_name = ref_cols.constraint_name
         AND cols.position = ref_cols.position
        WHERE c.owner = :owner
          AND c.table_name = :table_name
          AND c.constraint_type IN ('P', 'U', 'R', 'C')
        GROUP BY c.constraint_name, c.constraint_type
        ORDER BY
          CASE c.constraint_type
            WHEN 'P' THEN 1
            WHEN 'U' THEN 2
            WHEN 'R' THEN 3
            WHEN 'C' THEN 4
            ELSE 9
          END,
          c.constraint_name
        """
        fallback_sql = """
        SELECT
            c.constraint_name,
            CASE c.constraint_type
              WHEN 'P' THEN 'PRIMARY KEY'
              WHEN 'U' THEN 'UNIQUE'
              WHEN 'R' THEN 'FOREIGN KEY'
              WHEN 'C' THEN 'CHECK'
              ELSE c.constraint_type
            END AS constraint_type,
            LISTAGG(cols.column_name, ', ') WITHIN GROUP (ORDER BY cols.position) AS column_names,
            MAX(ref.table_name) AS referenced_table_name,
            LISTAGG(ref_cols.column_name, ', ') WITHIN GROUP (ORDER BY ref_cols.position) AS referenced_column_names,
            MAX(CASE WHEN c.constraint_type = 'C' THEN c.search_condition_vc ELSE '' END) AS check_clause
            /* '' AS check_clause */
        FROM user_constraints c
        JOIN user_cons_columns cols
          ON c.constraint_name = cols.constraint_name
        LEFT JOIN user_constraints ref
          ON c.r_constraint_name = ref.constraint_name
        LEFT JOIN user_cons_columns ref_cols
          ON ref.constraint_name = ref_cols.constraint_name
         AND cols.position = ref_cols.position
        WHERE c.table_name = :table_name
          AND c.constraint_type IN ('P', 'U', 'R', 'C')
        GROUP BY c.constraint_name, c.constraint_type
        ORDER BY
          CASE c.constraint_type
            WHEN 'P' THEN 1
            WHEN 'U' THEN 2
            WHEN 'R' THEN 3
            WHEN 'C' THEN 4
            ELSE 9
          END,
          c.constraint_name
        """
        no_check_sql = sql.replace(
            "MAX(CASE WHEN c.constraint_type = 'C' THEN c.search_condition_vc ELSE '' END) AS check_clause",
            "'' AS check_clause",
        )
        fallback_no_check_sql = fallback_sql.replace(
            "MAX(CASE WHEN c.constraint_type = 'C' THEN c.search_condition_vc ELSE '' END) AS check_clause",
            "'' AS check_clause",
        )
        rs = await asyncio.to_thread(
            self._run_query_sync,
            sql,
            {"owner": db_name.upper(), "table_name": tb_name.upper()},
        )
        if not rs.is_success:
            logger.info("oracle_constraint_query_fallback: %s", rs.error)
            rs = await asyncio.to_thread(
                self._run_query_sync,
                fallback_sql,
                {"table_name": tb_name.upper()},
            )
        if not rs.is_success:
            logger.info("oracle_constraint_query_without_check_clause: %s", rs.error)
            rs = await asyncio.to_thread(
                self._run_query_sync,
                no_check_sql,
                {"owner": db_name.upper(), "table_name": tb_name.upper()},
            )
        if not rs.is_success:
            logger.info("oracle_constraint_query_user_without_check_clause: %s", rs.error)
            rs = await asyncio.to_thread(
                self._run_query_sync,
                fallback_no_check_sql,
                {"table_name": tb_name.upper()},
            )
        return rs

    async def get_table_indexes(self, db_name: str, tb_name: str, **kwargs: Any) -> ResultSet:
        sql = """
        SELECT
            i.index_name,
            CASE
              WHEN MAX(CASE WHEN c.constraint_type = 'P' THEN 1 ELSE 0 END) = 1 THEN 'PRIMARY KEY INDEX'
              WHEN i.uniqueness = 'UNIQUE' THEN 'UNIQUE INDEX'
              ELSE 'INDEX'
            END AS index_type,
            LISTAGG(cols.column_name, ', ') WITHIN GROUP (ORDER BY cols.column_position) AS column_names,
            CASE
              WHEN COUNT(*) > 1 THEN 'YES'
              ELSE 'NO'
            END AS is_composite,
            '' AS index_comment
        FROM all_indexes i
        JOIN all_ind_columns cols
          ON i.owner = cols.index_owner
         AND i.index_name = cols.index_name
         AND i.table_name = cols.table_name
        LEFT JOIN all_constraints c
          ON c.owner = i.table_owner
         AND c.table_name = i.table_name
         AND c.index_name = i.index_name
         AND c.constraint_type IN ('P', 'U')
        WHERE i.table_owner = :owner
          AND i.table_name = :table_name
        GROUP BY i.index_name, i.uniqueness
        ORDER BY
          CASE
            WHEN MAX(CASE WHEN c.constraint_type = 'P' THEN 1 ELSE 0 END) = 1 THEN 1
            WHEN i.uniqueness = 'UNIQUE' THEN 2
            ELSE 3
          END,
          i.index_name
        """
        fallback_sql = """
        SELECT
            i.index_name,
            CASE
              WHEN MAX(CASE WHEN c.constraint_type = 'P' THEN 1 ELSE 0 END) = 1 THEN 'PRIMARY KEY INDEX'
              WHEN i.uniqueness = 'UNIQUE' THEN 'UNIQUE INDEX'
              ELSE 'INDEX'
            END AS index_type,
            LISTAGG(cols.column_name, ', ') WITHIN GROUP (ORDER BY cols.column_position) AS column_names,
            CASE
              WHEN COUNT(*) > 1 THEN 'YES'
              ELSE 'NO'
            END AS is_composite,
            '' AS index_comment
        FROM user_indexes i
        JOIN user_ind_columns cols
          ON i.index_name = cols.index_name
         AND i.table_name = cols.table_name
        LEFT JOIN user_constraints c
          ON c.table_name = i.table_name
         AND c.index_name = i.index_name
         AND c.constraint_type IN ('P', 'U')
        WHERE i.table_name = :table_name
        GROUP BY i.index_name, i.uniqueness
        ORDER BY
          CASE
            WHEN MAX(CASE WHEN c.constraint_type = 'P' THEN 1 ELSE 0 END) = 1 THEN 1
            WHEN i.uniqueness = 'UNIQUE' THEN 2
            ELSE 3
          END,
          i.index_name
        """
        rs = await asyncio.to_thread(
            self._run_query_sync,
            sql,
            {"owner": db_name.upper(), "table_name": tb_name.upper()},
        )
        if not rs.is_success:
            logger.info("oracle_index_query_fallback: %s", rs.error)
            rs = await asyncio.to_thread(
                self._run_query_sync,
                fallback_sql,
                {"table_name": tb_name.upper()},
            )
        return rs

    def query_check(self, db_name: str, sql: str) -> dict:
        result = {"msg": "", "has_star": False, "syntax_error": False}
        try:
            tree = sqlglot.parse_one(sql.strip().rstrip(";"), dialect="oracle")
            for _ in tree.find_all(exp.Star):
                result["has_star"] = True
                break
            for write_type in (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.TruncateTable):
                if tree.find(write_type):
                    result["msg"] = "查询接口不允许写操作"
                    break
        except sqlglot.errors.ParseError as e:
            result["syntax_error"] = True
            result["msg"] = f"SQL 语法错误：{sanitize_sqlglot_error(str(e))}"
        return result

    def filter_sql(self, sql: str, limit_num: int) -> str:
        sql_strip = sql.strip().rstrip(";")
        if limit_num > 0 and sql_strip.lower().startswith("select"):
            return f"SELECT * FROM ({sql_strip}) WHERE ROWNUM <= {limit_num}"
        return sql_strip

    async def query(
        self,
        db_name: str,
        sql: str,
        limit_num: int = 0,
        parameters: dict | None = None,
        **kw: Any,
    ) -> ResultSet:
        filtered_sql = self.filter_sql(sql, limit_num)
        return await asyncio.to_thread(self._run_query_sync, filtered_sql, parameters)

    def query_masking(self, db_name: str, sql: str, resultset: ResultSet) -> ResultSet:
        return resultset

    async def execute_check(self, db_name: str, sql: str) -> ReviewSet:
        review = ReviewSet(full_sql=sql)
        try:
            statements = sqlglot.parse(sql, dialect="oracle")
            for idx, stmt in enumerate(statements):
                item = SqlItem(id=idx + 1, sql=str(stmt))
                if stmt is None:
                    item.errlevel = 2
                    item.errormessage = "无法解析的 SQL 语句"
                elif isinstance(stmt, (exp.Drop, exp.TruncateTable)):
                    item.errlevel = 1
                    item.errormessage = "高风险操作，请确认已备份"
                item.stagestatus = "Audit completed"
                review.append(item)
        except Exception as e:
            review.error = str(e)
        return review

    async def execute(self, db_name: str, sql: str, **kw: Any) -> ReviewSet:
        review = ReviewSet(full_sql=sql)
        rs = await asyncio.to_thread(self._run_query_sync, sql, kw.get("parameters"))
        item = SqlItem(sql=sql)
        if rs.error:
            item.errlevel = 2
            item.errormessage = rs.error
        else:
            item.stagestatus = "Execute Successfully"
            item.affected_rows = rs.affected_rows
        review.append(item)
        review.error = rs.error
        review.is_executed = rs.is_success
        return review

    async def execute_workflow(self, workflow: Any) -> ReviewSet:
        return await self.execute(workflow.db_name, workflow.sql_content)

    async def processlist(
        self, command_type: str = "ALL", **kwargs: Any
    ) -> ResultSet:
        sql = """
        SELECT
            s.sid AS session_id,
            s.serial# AS serial,
            s.username AS username,
            s.machine AS host,
            s.program AS program,
            s.schemaname AS db_name,
            s.status AS state,
            CASE s.command
              WHEN 0 THEN ''
              WHEN 2 THEN 'INSERT'
              WHEN 3 THEN 'SELECT'
              WHEN 6 THEN 'UPDATE'
              WHEN 7 THEN 'DELETE'
              WHEN 44 THEN 'COMMIT'
              WHEN 45 THEN 'ROLLBACK'
              WHEN 47 THEN 'PL/SQL EXECUTE'
              ELSE TO_CHAR(s.command)
            END AS command,
            s.last_call_et AS time_seconds,
            ROUND((SYSDATE - s.logon_time) * 86400000) AS connection_age_ms,
            s.last_call_et * 1000 AS state_duration_ms,
            CASE
              WHEN s.sql_exec_start IS NOT NULL
              THEN ROUND((SYSDATE - s.sql_exec_start) * 86400000)
              ELSE NULL
            END AS active_duration_ms,
            CASE
              WHEN t.start_date IS NOT NULL
              THEN ROUND((SYSDATE - t.start_date) * 86400000)
              ELSE NULL
            END AS transaction_age_ms,
            s.last_call_et * 1000 AS duration_ms,
            'v$session' AS duration_source,
            s.sql_id AS sql_id,
            DBMS_LOB.SUBSTR(q.sql_fulltext, 4000, 1) AS sql_text,
            s.event AS event,
            s.blocking_session AS blocking_session
        FROM v$session s
        LEFT JOIN v$sql q
          ON s.sql_id = q.sql_id
         AND s.sql_child_number = q.child_number
        LEFT JOIN v$transaction t
          ON s.taddr = t.addr
        WHERE s.type = 'USER'
          AND s.audsid != USERENV('SESSIONID')
        ORDER BY s.last_call_et DESC
        """
        rs = await asyncio.to_thread(self._run_query_sync, sql, None)
        if rs.is_success:
            return rs

        logger.info("oracle_processlist_vsql_fallback: %s", rs.error)
        fallback_sql = """
        SELECT
            s.sid AS session_id,
            s.serial# AS serial,
            s.username AS username,
            s.machine AS host,
            s.program AS program,
            s.schemaname AS db_name,
            s.status AS state,
            CASE s.command
              WHEN 0 THEN ''
              WHEN 2 THEN 'INSERT'
              WHEN 3 THEN 'SELECT'
              WHEN 6 THEN 'UPDATE'
              WHEN 7 THEN 'DELETE'
              WHEN 44 THEN 'COMMIT'
              WHEN 45 THEN 'ROLLBACK'
              WHEN 47 THEN 'PL/SQL EXECUTE'
              ELSE TO_CHAR(s.command)
            END AS command,
            s.last_call_et AS time_seconds,
            ROUND((SYSDATE - s.logon_time) * 86400000) AS connection_age_ms,
            s.last_call_et * 1000 AS state_duration_ms,
            CASE
              WHEN s.sql_exec_start IS NOT NULL
              THEN ROUND((SYSDATE - s.sql_exec_start) * 86400000)
              ELSE NULL
            END AS active_duration_ms,
            CAST(NULL AS NUMBER) AS transaction_age_ms,
            s.last_call_et * 1000 AS duration_ms,
            'v$session' AS duration_source,
            s.sql_id AS sql_id,
            CAST(NULL AS VARCHAR2(4000)) AS sql_text,
            s.event AS event,
            s.blocking_session AS blocking_session
        FROM v$session s
        WHERE s.type = 'USER'
          AND s.audsid != USERENV('SESSIONID')
        ORDER BY s.last_call_et DESC
        """
        return await asyncio.to_thread(self._run_query_sync, fallback_sql, None)

    async def kill_connection(self, thread_id: int, serial: str | int | None = None) -> ResultSet:
        if serial in (None, ""):
            return ResultSet(error="Oracle Kill 会话必须提供 serial")
        sql = f"ALTER SYSTEM KILL SESSION '{int(thread_id)},{int(serial)}' IMMEDIATE"
        return await asyncio.to_thread(self._run_statement_sync, sql, None)

    def _ash_duration_expr(self, columns: set[str]) -> str:
        candidates = [
            column
            for column in ("TIME_WAITED", "TM_DELTA_TIME", "USECS_PER_ROW")
            if column in columns
        ]
        if not candidates:
            return "0"
        values = [f"NULLIF(ash.{column}, 0)" for column in candidates]
        if len(values) == 1:
            return f"ROUND({values[0]} / 1000)"
        return f"ROUND(COALESCE({', '.join(values)}) / 1000)"

    def _ash_column_expr(
        self,
        columns: set[str],
        candidates: tuple[str, ...],
        fallback: str,
    ) -> str:
        for column in candidates:
            if column in columns:
                return f"ash.{column}"
        return fallback

    def _ash_sql_text_join(self, source: str) -> tuple[str, str]:
        if source == "awr":
            return (
                "LEFT JOIN dba_hist_sqltext q ON ash.sql_id = q.sql_id",
                "DBMS_LOB.SUBSTR(q.sql_text, 4000, 1)",
            )
        return (
            "LEFT JOIN v$sql q ON ash.sql_id = q.sql_id",
            "DBMS_LOB.SUBSTR(q.sql_fulltext, 4000, 1)",
        )

    async def _ash_view_columns(self, view_name: str, source: str) -> ResultSet:
        rs = await asyncio.to_thread(
            self._run_query_sync,
            f"SELECT * FROM {view_name} WHERE 1 = 0",
            None,
        )
        if rs.error:
            label = "AWR" if source == "awr" else "ASH"
            rs.error = f"缺少 {label} 视图权限或视图不可用：{rs.error}"
        return rs

    async def ash_history(
        self,
        source: str = "ash",
        date_start: Any | None = None,
        date_end: Any | None = None,
        sql_keyword: str | None = None,
        min_duration_ms: int | None = None,
        limit_num: int = 50,
        offset: int = 0,
    ) -> ResultSet:
        view_name = (
            "dba_hist_active_sess_history"
            if source == "awr"
            else "v$active_session_history"
        )
        columns_rs = await self._ash_view_columns(view_name, source)
        if columns_rs.error:
            return columns_rs

        columns = {col.upper() for col in columns_rs.column_list}
        duration_expr = self._ash_duration_expr(columns)
        sql_text_join, sql_text_expr = self._ash_sql_text_join(source)
        serial_expr = self._ash_column_expr(columns, ("SESSION_SERIAL#", "SESSION_SERIAL"), "NULL")
        host_expr = self._ash_column_expr(columns, ("MACHINE",), "CAST(NULL AS VARCHAR2(255))")
        program_expr = self._ash_column_expr(columns, ("PROGRAM", "MODULE"), "CAST(NULL AS VARCHAR2(255))")
        state_expr = self._ash_column_expr(columns, ("SESSION_STATE",), "CAST(NULL AS VARCHAR2(255))")
        sql_id_expr = self._ash_column_expr(columns, ("SQL_ID",), "CAST(NULL AS VARCHAR2(255))")
        event_expr = self._ash_column_expr(columns, ("EVENT",), "CAST(NULL AS VARCHAR2(255))")
        blocking_expr = self._ash_column_expr(columns, ("BLOCKING_SESSION",), "CAST(NULL AS NUMBER)")
        sql = f"""
        SELECT * FROM (
            SELECT inner_q.*, ROWNUM AS rn FROM (
                SELECT
                    ash.sample_time AS collected_at,
                    ash.session_id AS session_id,
                    {serial_expr} AS serial,
                    COALESCE(u.username, TO_CHAR(ash.user_id)) AS username,
                    {host_expr} AS host,
                    {program_expr} AS program,
                    {state_expr} AS state,
                    {sql_id_expr} AS sql_id,
                    {sql_text_expr} AS sql_text,
                    {event_expr} AS event,
                    {blocking_expr} AS blocking_session,
                    CAST(NULL AS NUMBER) AS connection_age_ms,
                    {duration_expr} AS active_duration_ms,
                    {duration_expr} AS state_duration_ms,
                    CAST(NULL AS NUMBER) AS transaction_age_ms,
                    {duration_expr} AS duration_ms,
                    FLOOR(NVL(({duration_expr}), 0) / 1000) AS time_seconds,
                    'oracle_{source}_sample' AS duration_source
                FROM {view_name} ash
                {sql_text_join}
                LEFT JOIN all_users u ON ash.user_id = u.user_id
                WHERE 1 = 1
                  AND (:date_start IS NULL OR ash.sample_time >= :date_start)
                  AND (:date_end IS NULL OR ash.sample_time <= :date_end)
                  AND (:sql_keyword IS NULL OR LOWER({sql_text_expr}) LIKE :sql_keyword)
                  AND (:min_duration_ms IS NULL OR ({duration_expr}) >= :min_duration_ms)
                ORDER BY ash.sample_time DESC
            ) inner_q
            WHERE ROWNUM <= :row_limit
        )
        WHERE rn > :row_offset
        """
        params = {
            "date_start": date_start,
            "date_end": date_end,
            "sql_keyword": f"%{sql_keyword.lower()}%" if sql_keyword else None,
            "min_duration_ms": min_duration_ms,
            "row_limit": int(offset + limit_num),
            "row_offset": int(offset),
        }
        rs = await asyncio.to_thread(self._run_query_sync, sql, params)
        if rs.is_success:
            return rs

        logger.info("oracle_ash_vsql_fallback: %s", rs.error)
        fallback_sql = f"""
        SELECT * FROM (
            SELECT inner_q.*, ROWNUM AS rn FROM (
                SELECT
                    ash.sample_time AS collected_at,
                    ash.session_id AS session_id,
                    {serial_expr} AS serial,
                    COALESCE(u.username, TO_CHAR(ash.user_id)) AS username,
                    CAST(NULL AS VARCHAR2(255)) AS host,
                    CAST(NULL AS VARCHAR2(255)) AS program,
                    {state_expr} AS state,
                    {sql_id_expr} AS sql_id,
                    CAST(NULL AS VARCHAR2(4000)) AS sql_text,
                    {event_expr} AS event,
                    {blocking_expr} AS blocking_session,
                    CAST(NULL AS NUMBER) AS connection_age_ms,
                    {duration_expr} AS active_duration_ms,
                    {duration_expr} AS state_duration_ms,
                    CAST(NULL AS NUMBER) AS transaction_age_ms,
                    {duration_expr} AS duration_ms,
                    FLOOR(NVL(({duration_expr}), 0) / 1000) AS time_seconds,
                    'oracle_{source}_sample' AS duration_source
                FROM {view_name} ash
                LEFT JOIN all_users u ON ash.user_id = u.user_id
                WHERE 1 = 1
                  AND (:date_start IS NULL OR ash.sample_time >= :date_start)
                  AND (:date_end IS NULL OR ash.sample_time <= :date_end)
                  AND (:min_duration_ms IS NULL OR ({duration_expr}) >= :min_duration_ms)
                ORDER BY ash.sample_time DESC
            ) inner_q
            WHERE ROWNUM <= :row_limit
        )
        WHERE rn > :row_offset
        """
        if sql_keyword:
            rs.error = "当前账号无 V$SQL 权限，无法按 SQL 关键字过滤 ASH/AWR 历史"
            return rs
        return await asyncio.to_thread(self._run_query_sync, fallback_sql, params)

    async def collect_metrics(self) -> dict:
        return {"health": {"up": 1 if (await self.test_connection()).is_success else 0}}

    def get_supported_metric_groups(self) -> list[str]:
        return ["health"]
