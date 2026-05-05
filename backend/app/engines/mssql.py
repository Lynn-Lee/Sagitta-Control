"""
MSSQL 引擎最小可用实现。

当前聚焦数据字典与基础查询能力：
- 测试连接
- 获取库 / 表 / 列
- 获取表约束 / 索引
- 基础只读查询
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import sqlglot
import sqlglot.expressions as exp

from app.core.security import decrypt_field
from app.engines.models import ResultSet, ReviewSet, SqlItem
from app.engines.utils import normalize_engine_host, sanitize_sqlglot_error
from app.services.sql_audit import SqlAuditService

if TYPE_CHECKING:
    from app.models.instance import Instance


logger = logging.getLogger(__name__)


class MssqlEngine:
    name = "MssqlEngine"
    db_type = "mssql"

    def __init__(self, instance: Instance) -> None:
        self.instance = instance

        self._host = normalize_engine_host(instance.host)
        self._port = instance.port
        self._user = decrypt_field(instance.user)
        self._password = decrypt_field(instance.password)
        self._db_name = instance.db_name or "master"

    def _connect_sync(self, db_name: str | None = None):
        try:
            import pytds
        except ImportError:
            raise ImportError("python-tds 未安装，请先安装 backend 依赖") from None

        return pytds.connect(
            server=self._host,
            port=self._port,
            database=db_name or self._db_name,
            user=self._user,
            password=self._password,
            timeout=30,
            login_timeout=10,
            autocommit=True,
        )

    def _run_query_sync(
        self,
        sql: str,
        params: dict[str, Any] | tuple[Any, ...] | list[Any] | None = None,
        db_name: str | None = None,
    ) -> ResultSet:
        rs = ResultSet()
        conn = None
        try:
            conn = self._connect_sync(db_name)
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                if cur.description:
                    rs.column_list = [col[0] for col in cur.description]
                    rs.rows = cur.fetchall()
                    rs.affected_rows = len(rs.rows)
                else:
                    rs.affected_rows = cur.rowcount or 0
        except Exception as e:
            rs.error = str(e)
            logger.warning("mssql_query_error: %s", str(e))
        finally:
            if conn is not None:
                conn.close()
        return rs

    async def get_connection(self, db_name: str | None = None):
        return await asyncio.to_thread(self._connect_sync, db_name)

    async def test_connection(self) -> ResultSet:
        return await asyncio.to_thread(
            self._run_query_sync, "SELECT 1 AS result", None, self._db_name
        )

    def escape_string(self, value: str) -> str:
        return value.replace("]", "]]").replace("'", "''")

    async def get_all_databases(self) -> ResultSet:
        sql = """
        SELECT name
        FROM sys.databases
        WHERE database_id > 4
        ORDER BY name
        """
        return await asyncio.to_thread(self._run_query_sync, sql, None, self._db_name)

    async def get_all_tables(self, db_name: str, **kw: Any) -> ResultSet:
        schema = kw.get("schema", "dbo")
        sql = """
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
        """
        return await asyncio.to_thread(self._run_query_sync, sql, (schema,), db_name)

    async def get_all_columns_by_tb(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet:
        schema = kw.get("schema", "dbo")
        sql = """
        SELECT
            c.COLUMN_NAME AS column_name,
            CASE
              WHEN c.DATA_TYPE IN ('varchar', 'nvarchar', 'char', 'nchar', 'binary', 'varbinary')
                THEN c.DATA_TYPE + '(' + CASE WHEN c.CHARACTER_MAXIMUM_LENGTH = -1 THEN 'max' ELSE CAST(c.CHARACTER_MAXIMUM_LENGTH AS VARCHAR(16)) END + ')'
              WHEN c.DATA_TYPE IN ('decimal', 'numeric')
                THEN c.DATA_TYPE + '(' + CAST(c.NUMERIC_PRECISION AS VARCHAR(16)) + ',' + CAST(c.NUMERIC_SCALE AS VARCHAR(16)) + ')'
              ELSE c.DATA_TYPE
            END AS column_type,
            c.IS_NULLABLE AS is_nullable,
            c.COLUMN_DEFAULT AS column_default,
            CAST(ep.value AS NVARCHAR(4000)) AS column_comment
        FROM INFORMATION_SCHEMA.COLUMNS c
        LEFT JOIN sys.columns sc
          ON sc.object_id = OBJECT_ID(c.TABLE_SCHEMA + '.' + c.TABLE_NAME)
         AND sc.name = c.COLUMN_NAME
        LEFT JOIN sys.extended_properties ep
          ON ep.class = 1
         AND ep.major_id = sc.object_id
         AND ep.minor_id = sc.column_id
         AND ep.name = 'MS_Description'
        WHERE c.TABLE_SCHEMA = %s AND c.TABLE_NAME = %s
        ORDER BY c.ORDINAL_POSITION
        """
        return await asyncio.to_thread(self._run_query_sync, sql, (schema, tb_name), db_name)

    async def describe_table(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet:
        return await self.get_all_columns_by_tb(db_name, tb_name, **kw)

    async def get_table_constraints(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet:
        schema = kw.get("schema", "dbo")
        sql = """
        SELECT
            tc.CONSTRAINT_NAME AS constraint_name,
            tc.CONSTRAINT_TYPE AS constraint_type,
            COALESCE(
              STRING_AGG(kcu.COLUMN_NAME, ', ') WITHIN GROUP (ORDER BY kcu.ORDINAL_POSITION),
              MAX(CASE WHEN tc.CONSTRAINT_TYPE = 'CHECK' THEN check_col.name END),
              ''
            ) AS column_names,
            MAX(ccu.TABLE_NAME) AS referenced_table_name,
            STRING_AGG(ccu.COLUMN_NAME, ', ') WITHIN GROUP (ORDER BY kcu.ORDINAL_POSITION) AS referenced_column_names,
            COALESCE(MAX(CASE WHEN tc.CONSTRAINT_TYPE = 'CHECK' THEN scc.definition END), '') AS check_clause
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
        LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
          ON tc.CONSTRAINT_CATALOG = kcu.CONSTRAINT_CATALOG
         AND tc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
         AND tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
         AND tc.TABLE_NAME = kcu.TABLE_NAME
        LEFT JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
          ON tc.CONSTRAINT_CATALOG = rc.CONSTRAINT_CATALOG
         AND tc.CONSTRAINT_SCHEMA = rc.CONSTRAINT_SCHEMA
         AND tc.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
        LEFT JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu
          ON rc.UNIQUE_CONSTRAINT_CATALOG = ccu.CONSTRAINT_CATALOG
         AND rc.UNIQUE_CONSTRAINT_SCHEMA = ccu.CONSTRAINT_SCHEMA
         AND rc.UNIQUE_CONSTRAINT_NAME = ccu.CONSTRAINT_NAME
        LEFT JOIN sys.objects so
          ON so.name = tc.CONSTRAINT_NAME
         AND SCHEMA_NAME(so.schema_id) = tc.CONSTRAINT_SCHEMA
        LEFT JOIN sys.check_constraints scc
          ON scc.object_id = so.object_id
        LEFT JOIN sys.columns check_col
          ON check_col.object_id = scc.parent_object_id
         AND check_col.column_id = scc.parent_column_id
        WHERE tc.TABLE_SCHEMA = %s AND tc.TABLE_NAME = %s
        GROUP BY tc.CONSTRAINT_NAME, tc.CONSTRAINT_TYPE
        ORDER BY
          CASE tc.CONSTRAINT_TYPE
            WHEN 'PRIMARY KEY' THEN 1
            WHEN 'UNIQUE' THEN 2
            WHEN 'FOREIGN KEY' THEN 3
            WHEN 'CHECK' THEN 4
            ELSE 9
          END,
          tc.CONSTRAINT_NAME
        """
        return await asyncio.to_thread(self._run_query_sync, sql, (schema, tb_name), db_name)

    async def get_table_indexes(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet:
        schema = kw.get("schema", "dbo")
        sql = """
        SELECT
            i.name AS index_name,
            CASE
              WHEN i.is_primary_key = 1 THEN 'PRIMARY KEY INDEX'
              WHEN i.is_unique = 1 THEN 'UNIQUE INDEX'
              ELSE 'INDEX'
            END AS index_type,
            STRING_AGG(c.name, ', ') WITHIN GROUP (ORDER BY ic.key_ordinal) AS column_names,
            CASE WHEN COUNT(*) > 1 THEN 'YES' ELSE 'NO' END AS is_composite,
            '' AS index_comment
        FROM sys.indexes i
        JOIN sys.index_columns ic
          ON i.object_id = ic.object_id
         AND i.index_id = ic.index_id
        JOIN sys.columns c
          ON ic.object_id = c.object_id
         AND ic.column_id = c.column_id
        JOIN sys.tables t
          ON i.object_id = t.object_id
        JOIN sys.schemas s
          ON t.schema_id = s.schema_id
        WHERE s.name = %s
          AND t.name = %s
          AND i.name IS NOT NULL
          AND ic.is_included_column = 0
        GROUP BY i.name, i.is_primary_key, i.is_unique
        ORDER BY
          CASE
            WHEN i.is_primary_key = 1 THEN 1
            WHEN i.is_unique = 1 THEN 2
            ELSE 3
          END,
          i.name
        """
        return await asyncio.to_thread(self._run_query_sync, sql, (schema, tb_name), db_name)

    async def get_tables_metas_data(self, db_name: str, **kw: Any) -> list[dict[str, Any]]:
        schema = kw.get("schema", "dbo")
        sql = """
        SELECT
            t.name AS table_name,
            SUM(p.rows) AS table_rows
        FROM sys.tables t
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        JOIN sys.partitions p ON t.object_id = p.object_id AND p.index_id IN (0, 1)
        WHERE s.name = %s
        GROUP BY t.name
        ORDER BY t.name
        """
        rs = await asyncio.to_thread(self._run_query_sync, sql, (schema,), db_name)
        if not rs.is_success:
            return []
        return [dict(zip(rs.column_list, row, strict=False)) for row in rs.rows]

    def query_check(self, db_name: str, sql: str) -> dict:
        result: dict[str, Any] = {"msg": "", "has_star": False, "syntax_error": False}
        try:
            tree = sqlglot.parse_one(sql.strip().rstrip(";"), dialect="tsql")
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
        if (
            limit_num > 0
            and sql_strip.lower().startswith("select")
            and " top " not in sql_strip.lower()
        ):
            return f"SELECT TOP ({limit_num}) * FROM ({sql_strip}) AS sagitta_subq"
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
        return await asyncio.to_thread(self._run_query_sync, filtered_sql, parameters, db_name)

    async def explain_query(self, db_name: str, sql: str) -> ResultSet:
        explain_sql = f"SET SHOWPLAN_XML ON; {sql.strip().rstrip(';')}; SET SHOWPLAN_XML OFF;"
        return await asyncio.to_thread(self._run_query_sync, explain_sql, None, db_name)

    async def processlist(self, command_type: str = "ALL", **kwargs: Any) -> ResultSet:
        sql = """
        SELECT
            s.session_id AS session_id,
            s.login_name AS username,
            COALESCE(s.host_name, c.client_net_address, '') AS host,
            DB_NAME(COALESCE(r.database_id, s.database_id)) AS db_name,
            COALESCE(r.command, s.status) AS command,
            DATEDIFF(SECOND, COALESCE(r.start_time, s.last_request_start_time, s.login_time), SYSDATETIME()) AS time_seconds,
            DATEDIFF(MILLISECOND, COALESCE(r.start_time, s.last_request_start_time, s.login_time), SYSDATETIME()) AS duration_ms,
            DATEDIFF(MILLISECOND, COALESCE(r.start_time, s.last_request_start_time, s.login_time), SYSDATETIME()) AS state_duration_ms,
            'dm_exec_sessions' AS duration_source,
            COALESCE(r.status, s.status) AS state,
            st.text AS sql_text
        FROM sys.dm_exec_sessions s
        LEFT JOIN sys.dm_exec_connections c ON s.session_id = c.session_id
        LEFT JOIN sys.dm_exec_requests r ON s.session_id = r.session_id
        OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) st
        WHERE s.session_id <> @@SPID
        """
        if command_type and command_type != "ALL":
            sql += " AND COALESCE(r.command, s.status) = %s"
            params: tuple[Any, ...] | None = (command_type,)
        else:
            params = None
        sql += " ORDER BY duration_ms DESC"
        rs = await asyncio.to_thread(self._run_query_sync, sql, params, self._db_name)
        if rs.is_success:
            rs.rows = [self._row_to_dict(row, rs.column_list) for row in rs.rows]
        return rs

    async def kill_connection(self, thread_id: int) -> ResultSet:
        return await asyncio.to_thread(
            self._run_query_sync,
            f"KILL {int(thread_id)}",
            None,
            self._db_name,
        )

    def query_masking(self, db_name: str, sql: str, resultset: ResultSet) -> ResultSet:
        return resultset

    async def execute_check(self, db_name: str, sql: str) -> ReviewSet:
        return SqlAuditService.audit(self.db_type, db_name, sql)

    async def execute(self, db_name: str, sql: str, **kw: Any) -> ReviewSet:
        review = ReviewSet(full_sql=sql)
        rs = await asyncio.to_thread(self._run_query_sync, sql, kw.get("parameters"), db_name)
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

    async def collect_sql_activity(
        self,
        limit: int = 100,
        min_duration_ms: int = 1000,
    ) -> ResultSet:
        sql = """
        SELECT TOP (%s)
            'mssql_activity' AS source,
            'mssql:' + CAST(r.session_id AS VARCHAR(20)) + ':' + COALESCE(CONVERT(VARCHAR(64), r.sql_handle, 2), '') AS source_ref,
            DB_NAME(r.database_id) AS db_name,
            SUBSTRING(
              st.text,
              (r.statement_start_offset / 2) + 1,
              CASE
                WHEN r.statement_end_offset = -1 THEN LEN(CONVERT(NVARCHAR(MAX), st.text))
                ELSE (r.statement_end_offset - r.statement_start_offset) / 2 + 1
              END
            ) AS sql_text,
            r.total_elapsed_time AS duration_ms,
            s.login_name AS username,
            s.host_name AS client_host,
            r.command AS command,
            r.status AS state
        FROM sys.dm_exec_requests r
        JOIN sys.dm_exec_sessions s ON r.session_id = s.session_id
        CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) st
        WHERE r.session_id <> @@SPID
          AND r.total_elapsed_time >= %s
          AND st.text IS NOT NULL
        ORDER BY r.total_elapsed_time DESC
        """
        rs = await asyncio.to_thread(
            self._run_query_sync,
            sql,
            (int(limit), int(min_duration_ms)),
            self._db_name,
        )
        if rs.is_success:
            rs.rows = [self._row_to_dict(row, rs.column_list) for row in rs.rows]
        return rs

    async def collect_slow_queries(
        self,
        since: Any | None = None,
        limit: int = 100,
        min_duration_ms: int = 1000,
    ) -> ResultSet:
        return await self.collect_sql_activity(limit=limit, min_duration_ms=min_duration_ms)

    async def collect_metrics(self) -> dict[str, Any]:
        health_rs = await self.test_connection()
        if not health_rs.is_success:
            return {"health": {"up": 0, "error": health_rs.error}}

        version_rs = await asyncio.to_thread(
            self._run_query_sync,
            "SELECT CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128)) AS version",
            None,
            self._db_name,
        )
        database_rs = await asyncio.to_thread(
            self._run_query_sync,
            """
            SELECT
                COUNT(*) AS database_count,
                SUM(CASE WHEN state_desc = 'ONLINE' THEN 1 ELSE 0 END) AS online_database_count
            FROM sys.databases
            """,
            None,
            self._db_name,
        )
        session_rs = await asyncio.to_thread(
            self._run_query_sync,
            """
            SELECT
                COUNT(*) AS session_count,
                SUM(CASE WHEN is_user_process = 1 THEN 1 ELSE 0 END) AS user_session_count
            FROM sys.dm_exec_sessions
            """,
            None,
            self._db_name,
        )

        version_row = self._first_row_dict(version_rs)
        database_row = self._first_row_dict(database_rs)
        session_row = self._first_row_dict(session_rs)
        return {
            "health": {"up": 1},
            "version": {"value": version_row.get("version", "")},
            "databases": {
                "total": database_row.get("database_count"),
                "online": database_row.get("online_database_count"),
                "warning": database_rs.error,
            },
            "sessions": {
                "total": session_row.get("session_count"),
                "user": session_row.get("user_session_count"),
                "warning": session_rs.error,
            },
        }

    def get_supported_metric_groups(self) -> list[str]:
        return ["health", "version", "databases", "sessions"]

    @staticmethod
    def _row_to_dict(row: Any, columns: list[str]) -> dict[str, Any]:
        if isinstance(row, dict):
            return row
        if hasattr(row, "_asdict"):
            return dict(row._asdict())
        if isinstance(row, (tuple, list)):
            return dict(zip(columns, row, strict=False))
        return {"value": row}

    @classmethod
    def _first_row_dict(cls, rs: ResultSet) -> dict[str, Any]:
        if not rs.is_success or not rs.rows:
            return {}
        return cls._row_to_dict(rs.rows[0], rs.column_list)
