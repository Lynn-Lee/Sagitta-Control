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
from datetime import datetime
from threading import Lock
from typing import TYPE_CHECKING, Any

import oracledb
import sqlglot
import sqlglot.expressions as exp

from app.core.config import settings
from app.core.security import decrypt_field
from app.engines.models import ResultSet, ReviewSet, SqlItem
from app.engines.oracle_capacity import oracle_table_capacity_query_candidates
from app.engines.utils import normalize_engine_host, sanitize_sqlglot_error
from app.services.sql_audit import SqlAuditService

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
            f"{message}；当前 Sagitta Control 正在使用 python-oracledb Thin 模式。"
            "Oracle 11.2 及更早版本需安装 Instant Client，并将 ORACLE_DRIVER_MODE=thick。"
        )
    return message


def _oracle_datetime_param(value: Any | None) -> Any | None:
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


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

    def _connect_sync(self) -> Any:
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

    async def get_connection(self, db_name: str | None = None) -> Any:
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
        statement_id = f"SAGITTA_{uuid.uuid4().hex[:20].upper()}"
        explain_sql = (
            f"EXPLAIN PLAN SET STATEMENT_ID = '{statement_id}' FOR {sql.strip().rstrip(';')}"
        )
        rs = await asyncio.to_thread(self._run_statement_sync, explain_sql, None)
        if not rs.is_success:
            return rs
        display_sql = """
        SELECT plan_table_output
        FROM TABLE(DBMS_XPLAN.DISPLAY(NULL, :statement_id, 'TYPICAL +PREDICATE +ALIAS +COST +BYTES'))
        """
        plan_rs = await asyncio.to_thread(
            self._run_query_sync, display_sql, {"statement_id": statement_id}
        )
        cleanup_sql = "DELETE FROM plan_table WHERE statement_id = :statement_id"
        await asyncio.to_thread(
            self._run_statement_sync, cleanup_sql, {"statement_id": statement_id}
        )
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
        owner = db_name.upper()
        candidates = oracle_table_capacity_query_candidates(owner)
        rs = None
        zero_size_rows: list[dict[str, Any]] | None = None
        for candidate in candidates:
            rs = await asyncio.to_thread(self._run_query_sync, candidate.sql, candidate.params)
            if rs.is_success:
                columns = [str(col).lower() for col in rs.column_list]
                rows = [dict(zip(columns, row, strict=False)) for row in rs.rows]
                if rows and any((row.get("total_size") or 0) for row in rows):
                    return rows
                if rows and zero_size_rows is None:
                    zero_size_rows = rows
                logger.info("oracle_capacity_query_zero_size source=%s owner=%s", candidate.name, owner)
                continue
            logger.info("oracle_capacity_query_failed source=%s error=%s", candidate.name, rs.error)
        if zero_size_rows is not None:
            return zero_size_rows
        if rs is None or not rs.is_success:
            return []
        columns = [str(col).lower() for col in rs.column_list]
        return [dict(zip(columns, row, strict=False)) for row in rs.rows]

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

    def query_check(self, db_name: str, sql: str) -> dict[str, Any]:
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
        has_limit = re.search(r"\b(rownum|fetch\s+first|offset\s+\d+)\b", sql_strip, re.I)
        if limit_num > 0 and sql_strip.lower().startswith("select") and not has_limit:
            return f"SELECT * FROM ({sql_strip}) WHERE ROWNUM <= {limit_num}"
        return sql_strip

    async def query(
        self,
        db_name: str,
        sql: str,
        limit_num: int = 0,
        parameters: dict[str, Any] | None = None,
        **kw: Any,
    ) -> ResultSet:
        filtered_sql = self.filter_sql(sql, limit_num)
        return await asyncio.to_thread(self._run_query_sync, filtered_sql, parameters)

    def query_masking(self, db_name: str, sql: str, resultset: ResultSet) -> ResultSet:
        return resultset

    async def execute_check(self, db_name: str, sql: str) -> ReviewSet:
        return SqlAuditService.audit(self.db_type, db_name, sql)

    async def execute(self, db_name: str, sql: str, **kw: Any) -> ReviewSet:
        review = ReviewSet(full_sql=sql)
        rs = await asyncio.to_thread(self._run_statement_sync, sql, kw.get("parameters"))
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
        sql = workflow.content.sql_content if getattr(workflow, "content", None) else ""
        return await self.execute(workflow.db_name, sql)

    async def processlist(self, command_type: str = "ALL", **kwargs: Any) -> ResultSet:
        sql = """
        SELECT
            s.inst_id AS inst_id,
            s.sid AS session_id,
            s.serial# AS serial,
            p.spid AS process_id,
            s.username AS username,
            s.machine AS host,
            s.program AS program,
            s.module AS module,
            s.action AS action,
            s.client_identifier AS client_identifier,
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
            s.prev_sql_id AS prev_sql_id,
            s.sql_child_number AS sql_child_number,
            q.plan_hash_value AS plan_hash_value,
            DBMS_LOB.SUBSTR(q.sql_fulltext, 4000, 1) AS sql_text,
            s.event AS event,
            s.wait_class AS wait_class,
            s.seconds_in_wait AS seconds_in_wait,
            s.blocking_instance AS blocking_instance,
            s.blocking_session AS blocking_session,
            p.pga_used_mem AS pga_used_mem,
            p.pga_alloc_mem AS pga_alloc_mem,
            TO_CHAR(s.logon_time, 'YYYY-MM-DD HH24:MI:SS') AS logon_time
        FROM gv$session s
        LEFT JOIN gv$process p
          ON s.paddr = p.addr
         AND s.inst_id = p.inst_id
        LEFT JOIN gv$sql q
          ON s.sql_id = q.sql_id
         AND s.sql_child_number = q.child_number
         AND s.inst_id = q.inst_id
        LEFT JOIN gv$transaction t
          ON s.taddr = t.addr
         AND s.inst_id = t.inst_id
        WHERE s.type = 'USER'
          AND s.audsid != USERENV('SESSIONID')
        ORDER BY s.last_call_et DESC
        """
        rs = await asyncio.to_thread(self._run_query_sync, sql, None)
        if rs.is_success:
            return rs

        logger.info("oracle_processlist_gv_fallback: %s", rs.error)
        fallback_sql = """
        SELECT
            CAST(NULL AS NUMBER) AS inst_id,
            s.sid AS session_id,
            s.serial# AS serial,
            CAST(NULL AS VARCHAR2(64)) AS process_id,
            s.username AS username,
            s.machine AS host,
            s.program AS program,
            s.module AS module,
            s.action AS action,
            s.client_identifier AS client_identifier,
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
            s.prev_sql_id AS prev_sql_id,
            s.sql_child_number AS sql_child_number,
            q.plan_hash_value AS plan_hash_value,
            DBMS_LOB.SUBSTR(q.sql_fulltext, 4000, 1) AS sql_text,
            s.event AS event,
            s.wait_class AS wait_class,
            s.seconds_in_wait AS seconds_in_wait,
            CAST(NULL AS NUMBER) AS blocking_instance,
            s.blocking_session AS blocking_session,
            CAST(NULL AS NUMBER) AS pga_used_mem,
            CAST(NULL AS NUMBER) AS pga_alloc_mem,
            TO_CHAR(s.logon_time, 'YYYY-MM-DD HH24:MI:SS') AS logon_time
        FROM v$session s
        LEFT JOIN v$sql q
          ON s.sql_id = q.sql_id
         AND s.sql_child_number = q.child_number
        WHERE s.type = 'USER'
          AND s.audsid != USERENV('SESSIONID')
        ORDER BY s.last_call_et DESC
        """
        fallback_rs = await asyncio.to_thread(self._run_query_sync, fallback_sql, None)
        if fallback_rs.is_success:
            fallback_rs.warning = f"GV$ 会话视图不可用，已降级为 V$SESSION：{rs.error}"
            return fallback_rs

        logger.info("oracle_processlist_vsql_fallback: %s", fallback_rs.error)
        minimal_sql = """
        SELECT
            CAST(NULL AS NUMBER) AS inst_id,
            s.sid AS session_id,
            s.serial# AS serial,
            CAST(NULL AS VARCHAR2(64)) AS process_id,
            s.username AS username,
            s.machine AS host,
            s.program AS program,
            s.module AS module,
            s.action AS action,
            s.client_identifier AS client_identifier,
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
            s.prev_sql_id AS prev_sql_id,
            s.sql_child_number AS sql_child_number,
            CAST(NULL AS NUMBER) AS plan_hash_value,
            CAST(NULL AS VARCHAR2(4000)) AS sql_text,
            s.event AS event,
            s.wait_class AS wait_class,
            s.seconds_in_wait AS seconds_in_wait,
            CAST(NULL AS NUMBER) AS blocking_instance,
            s.blocking_session AS blocking_session,
            CAST(NULL AS NUMBER) AS pga_used_mem,
            CAST(NULL AS NUMBER) AS pga_alloc_mem,
            TO_CHAR(s.logon_time, 'YYYY-MM-DD HH24:MI:SS') AS logon_time
        FROM v$session s
        WHERE s.type = 'USER'
          AND s.audsid != USERENV('SESSIONID')
        ORDER BY s.last_call_et DESC
        """
        minimal_rs = await asyncio.to_thread(self._run_query_sync, minimal_sql, None)
        if minimal_rs.is_success:
            minimal_rs.warning = (
                "GV$ 或 V$SQL 会话详情不可用，已降级为 V$SESSION 基础字段："
                f"{rs.error}; {fallback_rs.error}"
            )
        return minimal_rs

    async def collect_sql_activity(
        self,
        limit: int = 100,
        min_duration_ms: int = 1000,
        window_minutes: int = 30,
        start_time: Any | None = None,
        end_time: Any | None = None,
    ) -> ResultSet:
        limit = max(1, min(int(limit or 100), 500))
        min_duration_ms = max(0, int(min_duration_ms or 0))
        window_minutes = max(1, min(int(window_minutes or 30), 1440))
        params = {
            "limit": limit,
            "min_duration_ms": min_duration_ms,
            "window_minutes": window_minutes,
            "date_start": _oracle_datetime_param(start_time),
            "date_end": _oracle_datetime_param(end_time),
        }
        warnings: list[str] = []

        sql_monitor_sql = """
        SELECT *
        FROM (
            SELECT
                'oracle_sql_monitor' AS source,
                'oracle:sql_monitor:' || m.inst_id || ':' || m.sql_id || ':'
                  || NVL(TO_CHAR(m.sql_exec_id), '') || ':'
                  || TO_CHAR(m.sql_exec_start, 'YYYYMMDDHH24MISS') AS source_ref,
                m.username AS db_name,
                SUBSTR(m.sql_text, 1, 4000) AS sql_text,
                ROUND(m.elapsed_time / 1000) AS duration_ms,
                ROUND(m.elapsed_time / 1000) AS elapsed_time_ms,
                ROUND(m.elapsed_time / 1000) AS avg_elapsed_ms,
                ROUND(m.elapsed_time / 1000) AS avg_duration_ms,
                ROUND(m.cpu_time / 1000) AS cpu_time_ms,
                m.username AS username,
                m.sql_id AS sql_id,
                m.sql_exec_id AS sql_exec_id,
                m.sql_exec_start AS occurred_at,
                m.sql_plan_hash_value AS plan_hash_value,
                m.status AS status,
                m.inst_id AS inst_id,
                m.sid AS session_id,
                m.session_serial# AS serial,
                m.process_name AS process_name,
                m.module AS module,
                m.action AS action,
                m.client_identifier AS client_identifier,
                m.px_servers_requested AS px_servers_requested,
                m.px_servers_allocated AS px_servers_allocated,
                m.buffer_gets AS buffer_gets,
                m.disk_reads AS disk_reads,
                CAST(NULL AS NUMBER) AS rows_sent
            FROM gv$sql_monitor m
            WHERE m.process_name = 'ora'
              AND m.sql_id IS NOT NULL
              AND m.sql_exec_start IS NOT NULL
              AND (:date_start IS NULL OR m.sql_exec_start >= :date_start)
              AND (:date_end IS NULL OR m.sql_exec_start <= :date_end)
              AND (:date_start IS NOT NULL OR m.sql_exec_start >= SYSDATE - (:window_minutes / 1440))
              AND ROUND(m.elapsed_time / 1000) >= :min_duration_ms
            ORDER BY m.elapsed_time DESC
        )
        WHERE ROWNUM <= :limit
        """
        rs = await asyncio.to_thread(self._run_query_sync, sql_monitor_sql, params)
        if rs.is_success and rs.rows:
            return rs
        if rs.error:
            warnings.append(f"GV$SQL_MONITOR 不可用：{rs.error}")

        awr_sql = """
        SELECT *
        FROM (
            SELECT
                'oracle_awr_sqlstat' AS source,
                'oracle:awr_sqlstat:' || h.instance_number || ':' || h.sql_id || ':'
                  || h.plan_hash_value || ':'
                  || TO_CHAR(MIN(s.begin_interval_time), 'YYYYMMDDHH24MI') || ':'
                  || TO_CHAR(MAX(s.end_interval_time), 'YYYYMMDDHH24MI') AS source_ref,
                MAX(h.parsing_schema_name) AS db_name,
                MAX(DBMS_LOB.SUBSTR(t.sql_text, 4000, 1)) AS sql_text,
                ROUND(SUM(h.elapsed_time_delta) / GREATEST(SUM(h.executions_delta), 1) / 1000) AS duration_ms,
                ROUND(SUM(h.elapsed_time_delta) / 1000) AS elapsed_time_ms,
                ROUND(SUM(h.elapsed_time_delta) / GREATEST(SUM(h.executions_delta), 1) / 1000) AS avg_elapsed_ms,
                ROUND(SUM(h.elapsed_time_delta) / GREATEST(SUM(h.executions_delta), 1) / 1000) AS avg_duration_ms,
                ROUND(SUM(h.cpu_time_delta) / 1000) AS cpu_time_ms,
                MAX(h.parsing_schema_name) AS username,
                h.sql_id AS sql_id,
                CAST(NULL AS NUMBER) AS sql_exec_id,
                MAX(s.end_interval_time) AS occurred_at,
                h.plan_hash_value AS plan_hash_value,
                SUM(h.executions_delta) AS executions,
                SUM(h.buffer_gets_delta) AS buffer_gets,
                SUM(h.disk_reads_delta) AS disk_reads,
                SUM(h.rows_processed_delta) AS rows_sent
            FROM dba_hist_sqlstat h
            JOIN dba_hist_snapshot s
              ON h.snap_id = s.snap_id
             AND h.dbid = s.dbid
             AND h.instance_number = s.instance_number
            LEFT JOIN dba_hist_sqltext t
              ON h.sql_id = t.sql_id
             AND h.dbid = t.dbid
            WHERE h.elapsed_time_delta > 0
              AND h.sql_id IS NOT NULL
              AND (:date_start IS NULL OR s.end_interval_time >= :date_start)
              AND (:date_end IS NULL OR s.begin_interval_time <= :date_end)
              AND (:date_start IS NOT NULL OR s.end_interval_time >= SYSDATE - (:window_minutes / 1440))
            GROUP BY h.instance_number, h.sql_id, h.plan_hash_value
            HAVING ROUND(SUM(h.elapsed_time_delta) / GREATEST(SUM(h.executions_delta), 1) / 1000) >= :min_duration_ms
            ORDER BY SUM(h.elapsed_time_delta) DESC
        )
        WHERE ROWNUM <= :limit
        """
        awr_rs = await asyncio.to_thread(self._run_query_sync, awr_sql, params)
        if awr_rs.is_success and awr_rs.rows:
            awr_rs.warning = "; ".join(warnings)
            return awr_rs
        if awr_rs.error:
            warnings.append(f"DBA_HIST_SQLSTAT 不可用：{awr_rs.error}")

        cursor_sql = """
        SELECT *
        FROM (
            SELECT
                'oracle_cursor_cache' AS source,
                'oracle:cursor_cache:' || inst_id || ':' || sql_id || ':'
                  || plan_hash_value || ':'
                  || TO_CHAR(MAX(last_active_time), 'YYYYMMDDHH24MI') AS source_ref,
                MIN(parsing_schema_name) AS db_name,
                MAX(DBMS_LOB.SUBSTR(sql_fulltext, 4000, 1)) AS sql_text,
                ROUND(SUM(elapsed_time) / GREATEST(SUM(executions), 1) / 1000) AS duration_ms,
                ROUND(SUM(elapsed_time) / 1000) AS elapsed_time_ms,
                ROUND(SUM(elapsed_time) / GREATEST(SUM(executions), 1) / 1000) AS avg_elapsed_ms,
                ROUND(SUM(elapsed_time) / GREATEST(SUM(executions), 1) / 1000) AS avg_duration_ms,
                ROUND(SUM(cpu_time) / 1000) AS cpu_time_ms,
                MIN(parsing_schema_name) AS username,
                sql_id AS sql_id,
                CAST(NULL AS NUMBER) AS sql_exec_id,
                MAX(last_active_time) AS occurred_at,
                plan_hash_value AS plan_hash_value,
                SUM(executions) AS executions,
                SUM(buffer_gets) AS buffer_gets,
                SUM(disk_reads) AS disk_reads,
                SUM(rows_processed) AS rows_sent
            FROM gv$sql
            WHERE elapsed_time > 0
              AND sql_id IS NOT NULL
              AND sql_text IS NOT NULL
              AND (:date_start IS NULL OR last_active_time >= :date_start)
              AND (:date_end IS NULL OR last_active_time <= :date_end)
              AND (:date_start IS NOT NULL OR last_active_time >= SYSDATE - (:window_minutes / 1440))
            GROUP BY inst_id, sql_id, plan_hash_value
            HAVING ROUND(SUM(elapsed_time) / GREATEST(SUM(executions), 1) / 1000) >= :min_duration_ms
            ORDER BY SUM(elapsed_time) DESC
        )
        WHERE ROWNUM <= :limit
        """
        cursor_rs = await asyncio.to_thread(self._run_query_sync, cursor_sql, params)
        if cursor_rs.is_success and cursor_rs.rows:
            cursor_rs.warning = "; ".join(warnings)
            return cursor_rs
        if cursor_rs.error:
            warnings.append(f"GV$SQL 不可用：{cursor_rs.error}")

        fallback = await self.processlist(command_type="ALL")
        if fallback.is_success:
            fallback.warning = (
                ("; ".join(warnings) + "；" if warnings else "")
                + "已降级为当前会话 SQL 活动"
            )
            mapped_rows = [
                {
                    str(col).lower(): value
                    for col, value in zip(fallback.column_list, row, strict=False)
                }
                if isinstance(row, (tuple, list))
                else row
                for row in fallback.rows
            ]
            fallback.column_list = [
                "source",
                "source_ref",
                "db_name",
                "sql_text",
                "duration_ms",
                "username",
                "client_host",
                "sql_id",
                "event",
                "state",
                "inst_id",
                "session_id",
                "serial",
                "wait_class",
                "seconds_in_wait",
            ]
            fallback.rows = [
                {
                    "source": "oracle_activity",
                    "source_ref": f"oracle:{row.get('session_id', '')}:{row.get('sql_id', '')}"
                    if isinstance(row, dict)
                    else "",
                    "db_name": row.get("db_name", "") if isinstance(row, dict) else "",
                    "sql_text": row.get("sql_text", "") if isinstance(row, dict) else "",
                    "duration_ms": row.get("duration_ms", 0) if isinstance(row, dict) else 0,
                    "username": row.get("username", "") if isinstance(row, dict) else "",
                    "client_host": row.get("host", "") if isinstance(row, dict) else "",
                    "sql_id": row.get("sql_id", "") if isinstance(row, dict) else "",
                    "event": row.get("event", "") if isinstance(row, dict) else "",
                    "state": row.get("state", "") if isinstance(row, dict) else "",
                    "inst_id": row.get("inst_id", "") if isinstance(row, dict) else "",
                    "session_id": row.get("session_id", "") if isinstance(row, dict) else "",
                    "serial": row.get("serial", "") if isinstance(row, dict) else "",
                    "wait_class": row.get("wait_class", "") if isinstance(row, dict) else "",
                    "seconds_in_wait": row.get("seconds_in_wait", "") if isinstance(row, dict) else "",
                }
                for row in mapped_rows[: int(limit)]
                if isinstance(row, dict)
                and row.get("sql_text")
                and int(float(row.get("duration_ms") or 0)) >= int(min_duration_ms)
            ]
            fallback.affected_rows = len(fallback.rows)
        return fallback

    async def kill_connection(self, thread_id: int, serial: str | int | None = None) -> ResultSet:
        if serial is None or serial == "":
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
            "dba_hist_active_sess_history" if source == "awr" else "v$active_session_history"
        )
        columns_rs = await self._ash_view_columns(view_name, source)
        if columns_rs.error:
            return columns_rs

        columns = {col.upper() for col in columns_rs.column_list}
        duration_expr = self._ash_duration_expr(columns)
        sql_text_join, sql_text_expr = self._ash_sql_text_join(source)
        serial_expr = self._ash_column_expr(columns, ("SESSION_SERIAL#", "SESSION_SERIAL"), "NULL")
        host_expr = self._ash_column_expr(columns, ("MACHINE",), "CAST(NULL AS VARCHAR2(255))")
        program_expr = self._ash_column_expr(
            columns, ("PROGRAM", "MODULE"), "CAST(NULL AS VARCHAR2(255))"
        )
        state_expr = self._ash_column_expr(
            columns, ("SESSION_STATE",), "CAST(NULL AS VARCHAR2(255))"
        )
        sql_id_expr = self._ash_column_expr(columns, ("SQL_ID",), "CAST(NULL AS VARCHAR2(255))")
        event_expr = self._ash_column_expr(columns, ("EVENT",), "CAST(NULL AS VARCHAR2(255))")
        blocking_expr = self._ash_column_expr(
            columns, ("BLOCKING_SESSION",), "CAST(NULL AS NUMBER)"
        )
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

    def _collect_metrics_sync(self) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            "health": {"up": 0},
            "connections": {},
            "stats": {},
            "queries": {},
            "missing_groups": {},
        }
        conn = None
        try:
            conn = self._connect_sync()
            metrics["health"]["up"] = 1
        except Exception as exc:
            error = _normalize_oracle_connect_error(exc)
            metrics["error"] = error
            metrics["missing_groups"]["health"] = error
            return metrics

        def fetch_one(group: str, sql: str, params: dict[str, Any] | None = None) -> Any:
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, params or {})
                    return cur.fetchone()
            except Exception as exc:
                metrics["missing_groups"][group] = _normalize_oracle_connect_error(exc)
                logger.info("oracle_metric_group_failed group=%s error=%s", group, exc)
                return None

        def fetch_all(group: str, sql: str, params: dict[str, Any] | None = None) -> Any:
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, params or {})
                    return cur.fetchall()
            except Exception as exc:
                metrics["missing_groups"][group] = _normalize_oracle_connect_error(exc)
                logger.info("oracle_metric_group_failed group=%s error=%s", group, exc)
                return []

        row = fetch_one(
            "version",
            """
            SELECT banner
            FROM v$version
            WHERE banner LIKE 'Oracle Database%'
              AND ROWNUM = 1
            """,
        )
        if row and row[0]:
            metrics["version"] = {"value": str(row[0])}

        row = fetch_one(
            "instance",
            """
            SELECT ROUND((SYSDATE - startup_time) * 86400) AS uptime_seconds
            FROM v$instance
            """,
        )
        if row and row[0] is not None:
            metrics["uptime_seconds"] = row[0]

        row = fetch_one(
            "connections",
            """
            SELECT
                COUNT(*) AS current_connections,
                SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END) AS active_sessions
            FROM v$session
            WHERE type = 'USER'
            """,
        )
        if row:
            metrics["connections"].update(
                {
                    "current": row[0],
                    "active_sessions": row[1],
                }
            )

        row = fetch_one(
            "connections",
            """
            SELECT value
            FROM v$parameter
            WHERE name = 'sessions'
            """,
        )
        if row and row[0] is not None:
            metrics["connections"]["max_connections"] = row[0]

        sysmetric_rows = fetch_all(
            "stats",
            """
            SELECT metric_name, value
            FROM v$sysmetric
            WHERE group_id = 2
              AND metric_name IN (
                'Executions Per Sec',
                'User Transaction Per Sec',
                'Average Active Sessions',
                'Current Logons Count',
                'Database Time Per Sec',
                'Database CPU Time Ratio',
                'Redo Generated Per Sec',
                'Logical Reads Per Sec',
                'Physical Reads Per Sec',
                'Hard Parse Count Per Sec',
                'Parse Failure Count Per Sec'
              )
            """,
        )
        for metric_name, value in sysmetric_rows:
            name = str(metric_name).lower()
            if name == "executions per sec":
                metrics["stats"]["qps"] = value
            elif name == "user transaction per sec":
                metrics["stats"]["tps"] = value
            elif name == "average active sessions":
                metrics["queries"]["active_sessions"] = value
            elif name == "current logons count":
                metrics["connections"].setdefault("current", value)
            elif name == "database time per sec":
                metrics["stats"]["db_time_per_sec"] = value
            elif name == "database cpu time ratio":
                metrics["stats"]["db_cpu_time_ratio"] = value
            elif name == "redo generated per sec":
                metrics["stats"]["redo_bytes_per_sec"] = value
            elif name == "logical reads per sec":
                metrics["stats"]["logical_reads_per_sec"] = value
            elif name == "physical reads per sec":
                metrics["stats"]["physical_reads_per_sec"] = value
            elif name == "hard parse count per sec":
                metrics["stats"]["hard_parse_per_sec"] = value
            elif name == "parse failure count per sec":
                metrics["stats"]["parse_failure_per_sec"] = value

        row = fetch_one(
            "stats",
            """
            SELECT COUNT(*)
            FROM v$session
            WHERE blocking_session IS NOT NULL
               OR event LIKE 'enq:%'
            """,
        )
        if row and row[0] is not None:
            metrics["stats"]["lock_waits"] = row[0]

        row = fetch_one(
            "stats",
            """
            SELECT COUNT(*)
            FROM v$transaction
            WHERE (SYSDATE - start_date) * 86400 >= 300
            """,
        )
        if row and row[0] is not None:
            metrics["stats"]["long_transactions"] = row[0]

        process_row = fetch_one(
            "connections",
            """
            SELECT
                MAX(CASE WHEN resource_name = 'processes' THEN current_utilization END),
                MAX(CASE WHEN resource_name = 'processes' THEN limit_value END)
            FROM v$resource_limit
            WHERE resource_name = 'processes'
            """,
        )
        if process_row:
            metrics["connections"]["processes_current"] = process_row[0]
            metrics["connections"]["processes_limit"] = process_row[1]

        metrics["wait_events"] = [
            {"event": row[0], "wait_class": row[1], "total_waits": row[2], "time_waited": row[3]}
            for row in fetch_all(
                "wait_events",
                """
                SELECT event, wait_class, total_waits, time_waited
                FROM (
                    SELECT event, wait_class, total_waits, time_waited
                    FROM v$system_event
                    WHERE wait_class <> 'Idle'
                    ORDER BY time_waited DESC
                )
                WHERE ROWNUM <= 10
                """,
            )
        ]
        metrics["active_wait_events"] = [
            {
                "inst_id": row[0],
                "event": row[1],
                "wait_class": row[2],
                "active_sessions": row[3],
                "sql_id": row[4],
                "seconds_in_wait": row[5],
            }
            for row in fetch_all(
                "active_wait_events",
                """
                SELECT inst_id, event, wait_class, active_sessions, sql_id, seconds_in_wait
                FROM (
                    SELECT
                        inst_id,
                        NVL(event, 'ON CPU') AS event,
                        NVL(wait_class, 'CPU') AS wait_class,
                        COUNT(*) AS active_sessions,
                        MAX(sql_id) AS sql_id,
                        SUM(seconds_in_wait) AS seconds_in_wait
                    FROM gv$session
                    WHERE status = 'ACTIVE'
                      AND type = 'USER'
                      AND NVL(wait_class, 'CPU') <> 'Idle'
                    GROUP BY inst_id, NVL(event, 'ON CPU'), NVL(wait_class, 'CPU')
                    ORDER BY active_sessions DESC, seconds_in_wait DESC
                )
                WHERE ROWNUM <= 20
                """,
            )
        ]
        metrics["blocking_sessions"] = [
            {
                "inst_id": row[0],
                "sid": row[1],
                "serial": row[2],
                "username": row[3],
                "event": row[4],
                "wait_class": row[5],
                "blocking_instance": row[6],
                "blocking_session": row[7],
                "seconds_in_wait": row[8],
                "sql_id": row[9],
                "sql_text": row[10],
            }
            for row in fetch_all(
                "blocking_sessions",
                """
                SELECT inst_id, sid, serial#, username, event, wait_class,
                       blocking_instance, blocking_session, seconds_in_wait,
                       sql_id, sql_text
                FROM (
                    SELECT
                        s.inst_id,
                        s.sid,
                        s.serial#,
                        s.username,
                        s.event,
                        s.wait_class,
                        s.blocking_instance,
                        s.blocking_session,
                        s.seconds_in_wait,
                        s.sql_id,
                        DBMS_LOB.SUBSTR(q.sql_fulltext, 1000, 1) AS sql_text
                    FROM gv$session s
                    LEFT JOIN gv$sql q
                      ON s.inst_id = q.inst_id
                     AND s.sql_id = q.sql_id
                     AND s.sql_child_number = q.child_number
                    WHERE s.blocking_session IS NOT NULL
                       OR s.event LIKE 'enq:%'
                    ORDER BY s.seconds_in_wait DESC
                )
                WHERE ROWNUM <= 20
                """,
            )
        ]
        metrics["long_transactions"] = [
            {
                "inst_id": row[0],
                "session_id": row[1],
                "serial": row[2],
                "username": row[3],
                "client_host": row[4],
                "sql_id": row[5],
                "sql_text": row[6],
                "duration_ms": row[7],
                "txn_start": row[8],
                "event": row[9],
                "blocking_instance": row[10],
                "blocking_session": row[11],
            }
            for row in fetch_all(
                "long_transactions",
                """
                SELECT inst_id, session_id, serial, username, client_host, sql_id,
                       sql_text, duration_ms, txn_start, event, blocking_instance,
                       blocking_session
                FROM (
                    SELECT
                        s.inst_id,
                        s.sid AS session_id,
                        s.serial# AS serial,
                        s.username,
                        s.machine AS client_host,
                        s.sql_id,
                        DBMS_LOB.SUBSTR(q.sql_fulltext, 1000, 1) AS sql_text,
                        ROUND((SYSDATE - t.start_date) * 86400000) AS duration_ms,
                        TO_CHAR(t.start_date, 'YYYY-MM-DD HH24:MI:SS') AS txn_start,
                        s.event,
                        s.blocking_instance,
                        s.blocking_session
                    FROM gv$transaction t
                    JOIN gv$session s
                      ON s.inst_id = t.inst_id
                     AND s.taddr = t.addr
                    LEFT JOIN gv$sql q
                      ON s.inst_id = q.inst_id
                     AND s.sql_id = q.sql_id
                     AND s.sql_child_number = q.child_number
                    ORDER BY duration_ms DESC
                )
                WHERE ROWNUM <= 20
                """,
            )
        ]
        metrics["tablespaces"] = [
            {
                "tablespace_name": row[0],
                "total_bytes": row[1],
                "used_bytes": row[2],
                "free_bytes": row[3],
                "used_pct": row[4],
                "autoextensible": row[5],
            }
            for row in fetch_all(
                "tablespaces",
                """
                SELECT
                    df.tablespace_name,
                    df.total_bytes,
                    df.total_bytes - NVL(fs.free_bytes, 0) AS used_bytes,
                    NVL(fs.free_bytes, 0) AS free_bytes,
                    ROUND((df.total_bytes - NVL(fs.free_bytes, 0)) / NULLIF(df.total_bytes, 0) * 100, 2) AS used_pct,
                    df.autoextensible
                FROM (
                    SELECT tablespace_name, SUM(bytes) AS total_bytes, MAX(autoextensible) AS autoextensible
                    FROM dba_data_files
                    GROUP BY tablespace_name
                ) df
                LEFT JOIN (
                    SELECT tablespace_name, SUM(bytes) AS free_bytes
                    FROM dba_free_space
                    GROUP BY tablespace_name
                ) fs ON fs.tablespace_name = df.tablespace_name
                ORDER BY used_pct DESC
                """,
            )
        ]
        metrics["temp_tablespaces"] = [
            {
                "tablespace_name": row[0],
                "used_bytes": row[1],
                "total_bytes": row[2],
                "used_pct": row[3],
            }
            for row in fetch_all(
                "temp_tablespaces",
                """
                SELECT
                    tf.tablespace_name,
                    NVL(th.used_bytes, 0) AS used_bytes,
                    tf.total_bytes AS total_bytes,
                    ROUND(NVL(th.used_bytes, 0) / NULLIF(tf.total_bytes, 0) * 100, 2) AS used_pct
                FROM (
                    SELECT tablespace_name, SUM(bytes) AS total_bytes
                    FROM dba_temp_files
                    GROUP BY tablespace_name
                ) tf
                LEFT JOIN (
                    SELECT tablespace_name, SUM(bytes_used) AS used_bytes
                    FROM v$temp_space_header
                    GROUP BY tablespace_name
                ) th ON th.tablespace_name = tf.tablespace_name
                ORDER BY used_pct DESC
                """,
            )
        ]
        metrics["top_segments"] = [
            {"owner": row[0], "segment_name": row[1], "segment_type": row[2], "bytes": row[3]}
            for row in fetch_all(
                "top_segments",
                """
                SELECT owner, segment_name, segment_type, bytes
                FROM (
                    SELECT owner, segment_name, segment_type, bytes
                    FROM dba_segments
                    ORDER BY bytes DESC
                )
                WHERE ROWNUM <= 20
                """,
            )
        ]
        metrics["fra"] = {}
        fra_row = fetch_one(
            "fra",
            """
            SELECT
                space_limit,
                space_used,
                ROUND(space_used / NULLIF(space_limit, 0) * 100, 2) AS used_pct
            FROM v$recovery_file_dest
            WHERE space_limit > 0
            """,
        )
        if fra_row:
            metrics["fra"] = {
                "space_limit": fra_row[0],
                "space_used": fra_row[1],
                "used_pct": fra_row[2],
            }
        archive_row = fetch_one(
            "archive",
            """
            SELECT
                MAX(completion_time),
                COUNT(*)
            FROM v$archived_log
            WHERE completion_time >= SYSDATE - 1
            """,
        )
        if archive_row:
            metrics["archive"] = {
                "last_completion_time": archive_row[0],
                "logs_last_24h": archive_row[1],
            }
        metrics["data_guard"] = [
            {"name": row[0], "value": row[1], "unit": row[2], "time_computed": row[3]}
            for row in fetch_all(
                "data_guard",
                """
                SELECT name, value, unit, time_computed
                FROM v$dataguard_stats
                WHERE name IN ('transport lag', 'apply lag', 'apply finish time')
                """,
            )
        ]
        metrics["top_sql"] = [
            {
                "sql_id": row[0],
                "schema_name": row[1],
                "module": row[2],
                "executions": row[3],
                "elapsed_time_ms": row[4],
                "avg_elapsed_ms": row[5],
                "buffer_gets": row[6],
                "disk_reads": row[7],
                "sql_text": row[8],
            }
            for row in fetch_all(
                "top_sql",
                """
                SELECT
                    sql_id,
                    parsing_schema_name,
                    module,
                    executions,
                    elapsed_time_ms,
                    avg_elapsed_ms,
                    buffer_gets,
                    disk_reads,
                    sql_text
                FROM (
                    SELECT
                        sql_id,
                        parsing_schema_name,
                        module,
                        executions,
                        ROUND(elapsed_time / 1000) AS elapsed_time_ms,
                        ROUND(elapsed_time / NULLIF(executions, 0) / 1000) AS avg_elapsed_ms,
                        buffer_gets,
                        disk_reads,
                        SUBSTR(sql_text, 1, 1000) AS sql_text
                    FROM v$sql
                    WHERE sql_text IS NOT NULL
                    ORDER BY elapsed_time DESC
                )
                WHERE ROWNUM <= 20
                """,
            )
        ]
        metrics["longops"] = [
            {
                "inst_id": row[0],
                "session_id": row[1],
                "sql_id": row[2],
                "opname": row[3],
                "sofar": row[4],
                "totalwork": row[5],
                "percent": row[6],
                "elapsed_seconds": row[7],
                "time_remaining_seconds": row[8],
            }
            for row in fetch_all(
                "longops",
                """
                SELECT inst_id, sid, sql_id, opname, sofar, totalwork, percent,
                       elapsed_seconds, time_remaining_seconds
                FROM (
                    SELECT
                        inst_id,
                        sid,
                        sql_id,
                        opname,
                        sofar,
                        totalwork,
                        ROUND(sofar * 100 / NULLIF(totalwork, 0)) AS percent,
                        elapsed_seconds,
                        CASE
                          WHEN sofar = 0 THEN 0
                          ELSE ROUND(elapsed_seconds * (totalwork - sofar) / NULLIF(sofar, 0))
                        END AS time_remaining_seconds
                    FROM gv$session_longops
                    WHERE sofar <> totalwork
                      AND totalwork > 0
                    ORDER BY elapsed_seconds DESC
                )
                WHERE ROWNUM <= 20
                """,
            )
        ]

        if conn is not None:
            conn.close()
        return metrics

    async def collect_metrics(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._collect_metrics_sync)

    def get_supported_metric_groups(self) -> list[str]:
        return [
            "health",
            "version",
            "instance",
            "connections",
            "stats",
            "wait_events",
            "active_wait_events",
            "blocking_sessions",
            "long_transactions",
            "longops",
            "tablespaces",
            "temp_tablespaces",
            "fra",
            "archive",
            "data_guard",
            "top_sql",
        ]
