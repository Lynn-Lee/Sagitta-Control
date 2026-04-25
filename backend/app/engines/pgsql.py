"""
PostgreSQL 引擎完整实现（Sprint 2）。
使用 asyncpg 异步驱动，参数化查询防注入。
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import asyncpg
import sqlglot
import sqlglot.expressions as exp

from app.core.security import decrypt_field
from app.engines.models import ResultSet, ReviewSet, SqlItem
from app.engines.utils import normalize_engine_host, sanitize_sqlglot_error

if TYPE_CHECKING:
    from app.models.instance import Instance

logger = logging.getLogger(__name__)


class PgSQLEngine:
    name = "PgSQLEngine"
    db_type = "pgsql"

    def __init__(self, instance: Instance) -> None:
        self.instance = instance
        self._host = normalize_engine_host(instance.host)
        self._port = instance.port
        self._user = decrypt_field(instance.user)
        self._password = decrypt_field(instance.password)
        self._db_name = instance.db_name or "postgres"
        self._pool: asyncpg.Pool | None = None

    # ── 连接管理 ──────────────────────────────────────────────

    async def _get_pool(self, db_name: str | None = None) -> asyncpg.Pool:
        target_db = db_name or self._db_name
        if self._pool is None or self._pool.get_size() == 0:
            self._pool = await asyncpg.create_pool(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                database=target_db,
                min_size=1,
                max_size=5,
                command_timeout=30,
            )
        return self._pool

    async def get_connection(self, db_name: str | None = None):
        pool = await self._get_pool(db_name)
        return pool

    async def resolve_table_schemas(self, db_name: str, table_names: list[str]) -> dict[str, list[str]]:
        normalized_names = sorted({name.strip() for name in table_names if name and name.strip()})
        if not normalized_names:
            return {}

        sql = """
            SELECT table_name, table_schema
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_name = ANY($1::text[])
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_name, table_schema
        """
        rs = await self._raw_query(db_name=db_name, sql=sql, args=[normalized_names])
        mapping = {name: [] for name in normalized_names}
        if rs.error:
            return mapping

        for row in rs.rows:
            table_name, table_schema = row[0], row[1]
            mapping.setdefault(str(table_name), []).append(str(table_schema))
        return mapping

    async def test_connection(self) -> ResultSet:
        rs = ResultSet()
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            rs.rows = [("ok",)]
            rs.column_list = ["result"]
        except Exception as e:
            rs.error = str(e)
        return rs

    def escape_string(self, value: str) -> str:
        return value.replace("'", "''")

    # ── 元数据 ────────────────────────────────────────────────

    async def get_all_databases(self) -> ResultSet:
        sql = "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname"
        return await self.query(db_name=self._db_name, sql=sql, limit_num=0)

    async def get_all_tables(self, db_name: str, **kwargs: Any) -> ResultSet:
        schema = kwargs.get("schema", "public")
        sql = """SELECT table_name FROM information_schema.tables
                 WHERE table_schema = $1 AND table_type = 'BASE TABLE'
                 ORDER BY table_name"""
        return await self._raw_query(db_name=db_name, sql=sql, args=[schema])

    async def get_all_columns_by_tb(self, db_name: str, tb_name: str, **kwargs: Any) -> ResultSet:
        schema = kwargs.get("schema", "public")
        sql = """SELECT column_name, data_type, is_nullable, column_default,
                        col_description((table_schema||'.'||table_name)::regclass::oid, ordinal_position) AS column_comment
                 FROM information_schema.columns
                 WHERE table_name = $1 AND table_schema = $2
                 ORDER BY ordinal_position"""
        return await self._raw_query(db_name=db_name, sql=sql, args=[tb_name, schema])

    async def describe_table(self, db_name: str, tb_name: str, **kwargs: Any) -> ResultSet:
        schema = kwargs.get("schema", "public")
        sql = """SELECT column_name, data_type, character_maximum_length,
                        is_nullable, column_default, col_description(
                            (table_schema||'.'||table_name)::regclass::oid,
                            ordinal_position) AS comment
                 FROM information_schema.columns
                 WHERE table_name = $1 AND table_schema = $2
                 ORDER BY ordinal_position"""
        return await self._raw_query(db_name=db_name, sql=sql, args=[tb_name, schema])

    async def get_tables_metas_data(self, db_name: str, **kwargs: Any) -> list[dict[str, Any]]:
        sql = """SELECT relname AS table_name,
                        pg_stat_get_live_tuples(c.oid) AS table_rows,
                        pg_total_relation_size(c.oid) AS total_size,
                        obj_description(c.oid) AS comment
                 FROM pg_class c
                 JOIN pg_namespace n ON n.oid = c.relnamespace
                 WHERE c.relkind = 'r' AND n.nspname = 'public'
                 ORDER BY relname"""
        rs = await self._raw_query(db_name=db_name, sql=sql, args=[])
        cols = rs.column_list
        return [dict(zip(cols, row, strict=False)) for row in rs.rows]

    async def get_table_constraints(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        schema = kwargs.get("schema", "public")
        sql = """SELECT
                    con.conname AS constraint_name,
                    CASE con.contype
                      WHEN 'p' THEN 'PRIMARY KEY'
                      WHEN 'u' THEN 'UNIQUE'
                      WHEN 'f' THEN 'FOREIGN KEY'
                      WHEN 'c' THEN 'CHECK'
                      ELSE con.contype::text
                    END AS constraint_type,
                    COALESCE(cols.column_names, '') AS column_names,
                    COALESCE(ref_tbl.relname, '') AS referenced_table_name,
                    COALESCE(ref_cols.referenced_column_names, '') AS referenced_column_names,
                    CASE
                      WHEN con.contype = 'c' THEN pg_get_constraintdef(con.oid, true)
                      ELSE ''
                    END AS check_clause
                 FROM pg_constraint con
                 JOIN pg_class tbl
                   ON tbl.oid = con.conrelid
                 JOIN pg_namespace ns
                   ON ns.oid = tbl.relnamespace
                 LEFT JOIN LATERAL (
                   SELECT string_agg(att.attname, ', ' ORDER BY ck.ord) AS column_names
                   FROM unnest(COALESCE(con.conkey, ARRAY[]::smallint[])) WITH ORDINALITY AS ck(attnum, ord)
                   JOIN pg_attribute att
                     ON att.attrelid = con.conrelid
                    AND att.attnum = ck.attnum
                 ) cols ON TRUE
                 LEFT JOIN pg_class ref_tbl
                   ON ref_tbl.oid = con.confrelid
                 LEFT JOIN LATERAL (
                   SELECT string_agg(att.attname, ', ' ORDER BY fk.ord) AS referenced_column_names
                   FROM unnest(COALESCE(con.confkey, ARRAY[]::smallint[])) WITH ORDINALITY AS fk(attnum, ord)
                   JOIN pg_attribute att
                     ON att.attrelid = con.confrelid
                    AND att.attnum = fk.attnum
                 ) ref_cols ON TRUE
                 WHERE ns.nspname = $1
                   AND tbl.relname = $2
                   AND con.contype IN ('p', 'u', 'f', 'c')
                 ORDER BY
                   CASE con.contype
                     WHEN 'p' THEN 1
                     WHEN 'u' THEN 2
                     WHEN 'f' THEN 3
                     WHEN 'c' THEN 4
                     ELSE 9
                   END,
                   con.conname"""
        return await self._raw_query(db_name=db_name, sql=sql, args=[schema, tb_name])

    async def get_table_indexes(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        schema = kwargs.get("schema", "public")
        sql = r"""SELECT
                    indexname AS index_name,
                    CASE
                      WHEN indexdef ILIKE '%% unique index %%' THEN 'UNIQUE INDEX'
                      ELSE 'INDEX'
                    END AS index_type,
                    COALESCE(
                      substring(indexdef FROM '\((.*)\)'),
                      ''
                    ) AS column_names,
                    CASE
                      WHEN position(',' in COALESCE(substring(indexdef FROM '\((.*)\)'), '')) > 0 THEN 'YES'
                      ELSE 'NO'
                    END AS is_composite,
                    '' AS index_comment,
                    indexdef AS index_definition
                 FROM pg_indexes
                 WHERE schemaname = $1 AND tablename = $2
                 ORDER BY
                   CASE
                     WHEN indexname = $2 || '_pkey' THEN 1
                     WHEN indexdef ILIKE '%% unique index %%' THEN 2
                     ELSE 3
                   END,
                   indexname"""
        return await self._raw_query(db_name=db_name, sql=sql, args=[schema, tb_name])

    # ── 查询 ──────────────────────────────────────────────────

    def query_check(self, db_name: str, sql: str) -> dict[str, Any]:
        result: dict[str, Any] = {"msg": "", "has_star": False, "syntax_error": False}
        sql_strip = sql.strip().rstrip(";")
        try:
            tree = sqlglot.parse_one(sql_strip, dialect="postgres")
            for _ in tree.find_all(exp.Star):
                result["has_star"] = True
                break
            write_types = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.TruncateTable)
            for wt in write_types:
                if tree.find(wt):
                    result["msg"] = "查询接口不允许写操作"
                    break
        except sqlglot.errors.ParseError as e:
            result["syntax_error"] = True
            result["msg"] = f"SQL 语法错误：{sanitize_sqlglot_error(str(e))}"
        return result

    def filter_sql(self, sql: str, limit_num: int) -> str:
        sql_strip = sql.strip().rstrip(";")
        if limit_num > 0 and sql_strip.lower().startswith("select") and "limit" not in sql_strip.lower():
            return f"{sql_strip} LIMIT {limit_num}"
        return sql_strip

    async def _raw_query(
        self, db_name: str, sql: str, args: list[Any]
    ) -> ResultSet:
        """内部方法：asyncpg 原生参数化查询（$1, $2 占位符）。"""
        rs = ResultSet()
        start = time.monotonic()
        try:
            pool = await self._get_pool(db_name)
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, *args)
                if rows:
                    rs.column_list = list(rows[0].keys())
                    rs.rows = [tuple(row.values()) for row in rows]
                else:
                    rs.column_list = []
                    rs.rows = []
                rs.affected_rows = len(rs.rows)
        except Exception as e:
            rs.error = str(e)
            logger.warning("pgsql_query_error: %s", str(e))
        finally:
            rs.cost_time = int((time.monotonic() - start) * 1000)
        return rs

    async def query(
        self,
        db_name: str,
        sql: str,
        limit_num: int = 0,
        parameters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ResultSet:
        """
        执行查询。
        parameters 为 dict 时转换为 asyncpg 的位置参数格式。
        """
        rs = ResultSet()
        start = time.monotonic()
        try:
            pool = await self._get_pool(db_name)
            async with pool.acquire() as conn, conn.transaction():
                search_path = kwargs.get("search_path")
                if search_path:
                    await conn.fetchval(
                        "SELECT set_config('search_path', $1, true)",
                        search_path,
                    )

                # 将 %(key)s 风格参数转换为 $1,$2 风格
                exec_sql, args = self._convert_params(sql, parameters)
                if limit_num > 0 and "limit" not in exec_sql.lower():
                    exec_sql = f"{exec_sql.rstrip(';')} LIMIT {limit_num}"
                rows = await conn.fetch(exec_sql, *args)
                if rows:
                    rs.column_list = list(rows[0].keys())
                    rs.rows = [tuple(row.values()) for row in rows]
                else:
                    rs.column_list = []
                    rs.rows = []
                rs.affected_rows = len(rs.rows)
        except Exception as e:
            rs.error = str(e)
            logger.warning("pgsql_query_error: %s", str(e))
        finally:
            rs.cost_time = int((time.monotonic() - start) * 1000)
        return rs

    def _convert_params(
        self, sql: str, parameters: dict[str, Any] | None
    ) -> tuple[str, list[Any]]:
        """将 %(key)s 风格参数转为 asyncpg 的 $1,$2 风格。"""
        if not parameters:
            return sql, []
        import re
        keys = []
        def replacer(m: re.Match) -> str:
            key = m.group(1)
            if key not in keys:
                keys.append(key)
            return f"${keys.index(key) + 1}"
        converted = re.sub(r"%\((\w+)\)s", replacer, sql)
        args = [parameters[k] for k in keys]
        return converted, args

    def query_masking(self, db_name: str, sql: str, resultset: ResultSet) -> ResultSet:
        return resultset  # 由 services.masking 处理

    # ── 审核与执行 ────────────────────────────────────────────

    async def execute_check(self, db_name: str, sql: str) -> ReviewSet:
        review = ReviewSet(full_sql=sql)
        try:
            statements = sqlglot.parse(sql, dialect="postgres")
            for idx, stmt in enumerate(statements):
                item = SqlItem(id=idx + 1, sql=str(stmt) if stmt else sql)
                if stmt is None:
                    item.errlevel = 2
                    item.errormessage = "无法解析的 SQL 语句"
                elif isinstance(stmt, (exp.Update, exp.Delete)):
                    if not stmt.find(exp.Where):
                        item.errlevel = 2
                        item.errormessage = "UPDATE/DELETE 缺少 WHERE 条件"
                elif isinstance(stmt, (exp.Drop, exp.TruncateTable)):
                    item.errlevel = 1
                    item.errormessage = "高风险操作，请确认已备份"
                item.stagestatus = "Audit completed"
                review.append(item)
        except Exception as e:
            review.error = str(e)
        return review

    async def execute(self, db_name: str, sql: str, **kwargs: Any) -> ReviewSet:
        review = ReviewSet(full_sql=sql)
        try:
            pool = await self._get_pool(db_name)
            async with pool.acquire() as conn, conn.transaction():
                result = await conn.execute(sql)
                item = SqlItem(sql=sql, stagestatus="Execute Successfully")
                # result 格式如 "INSERT 0 1"
                try:
                    item.affected_rows = int(result.split()[-1])
                except Exception:
                    item.affected_rows = 0
                review.append(item)
            review.is_executed = True
        except Exception as e:
            review.error = str(e)
            review.append(SqlItem(sql=sql, errlevel=2, errormessage=str(e)))
        return review

    async def execute_workflow(self, workflow: Any) -> ReviewSet:
        return ReviewSet(error="Sprint 3 实现")

    # ── 可选能力 ──────────────────────────────────────────────

    async def processlist(self, command_type: str = "Query", **kwargs: Any) -> ResultSet:
        sql = """SELECT pid AS session_id,
                        usename AS username,
                        client_addr::text AS host,
                        application_name AS program,
                        datname AS db_name,
                        state,
                        CASE WHEN state = 'active' THEN 'Query' ELSE state END AS command,
                        round(extract(epoch from (now()-backend_start)) * 1000)::bigint AS connection_age_ms,
                        extract(epoch from (now()-state_change))::int AS time_seconds,
                        round(extract(epoch from (now()-state_change)) * 1000)::bigint AS state_duration_ms,
                        CASE
                          WHEN state = 'active' AND query_start IS NOT NULL
                          THEN round(extract(epoch from (now()-query_start)) * 1000)::bigint
                          ELSE NULL
                        END AS active_duration_ms,
                        CASE
                          WHEN xact_start IS NOT NULL
                          THEN round(extract(epoch from (now()-xact_start)) * 1000)::bigint
                          ELSE NULL
                        END AS transaction_age_ms,
                        round(extract(epoch from (now()-state_change)) * 1000)::bigint AS duration_ms,
                        'pg_stat_activity' AS duration_source,
                        query AS sql_text
                 FROM pg_stat_activity
                 WHERE pid != pg_backend_pid()
                 ORDER BY state_change"""
        return await self._raw_query(db_name=self._db_name, sql=sql, args=[])

    async def kill_connection(self, thread_id: int) -> ResultSet:
        sql = "SELECT pg_terminate_backend($1)"
        return await self._raw_query(db_name=self._db_name, sql=sql, args=[thread_id])

    async def get_variables(self, variables: list[str] | None = None) -> ResultSet:
        if variables:
            placeholders = ",".join(f"${i+1}" for i in range(len(variables)))
            sql = f"SELECT name, setting FROM pg_settings WHERE name = ANY(ARRAY[{placeholders}])"
            return await self._raw_query(db_name=self._db_name, sql=sql, args=variables)
        return await self._raw_query(
            db_name=self._db_name,
            sql="SELECT name, setting FROM pg_settings ORDER BY name",
            args=[],
        )

    async def collect_metrics(self) -> dict[str, Any]:
        rs = await self.test_connection()
        return {"health": {"up": 1 if rs.is_success else 0}}

    async def collect_slow_queries(
        self,
        since: Any | None = None,
        limit: int = 100,
        min_duration_ms: int = 1000,
    ) -> ResultSet:
        """Collect PostgreSQL slow statement summaries from pg_stat_statements."""
        columns_rs = await self._raw_query(
            db_name=self._db_name,
            sql="""
                SELECT attname
                FROM pg_attribute
                WHERE attrelid = to_regclass('pg_stat_statements')
                  AND attnum > 0
                  AND NOT attisdropped
            """,
            args=[],
        )
        if columns_rs.error:
            return columns_rs

        columns = {str(row[0]) for row in columns_rs.rows}
        if not columns:
            return ResultSet(error="pg_stat_statements extension is not available")

        if "mean_exec_time" in columns:
            duration_expr = "mean_exec_time"
        elif "mean_time" in columns:
            duration_expr = "mean_time"
        elif "total_exec_time" in columns and "calls" in columns:
            duration_expr = "total_exec_time / NULLIF(calls, 0)"
        elif "total_time" in columns and "calls" in columns:
            duration_expr = "total_time / NULLIF(calls, 0)"
        else:
            return ResultSet(error="pg_stat_statements does not expose execution time columns")

        sql = f"""
            SELECT
              'pgsql_statements' AS source,
              queryid::text AS source_ref,
              current_database() AS db_name,
              query AS sql_text,
              round(({duration_expr})::numeric)::bigint AS duration_ms,
              rows AS rows_sent,
              calls
            FROM pg_stat_statements
            WHERE {duration_expr} >= $2
            ORDER BY {duration_expr} DESC
            LIMIT $1
        """
        return await self._raw_query(
            db_name=self._db_name,
            sql=sql,
            args=[int(limit), max(0, int(min_duration_ms))],
        )

    async def explain_query(self, db_name: str, sql: str) -> ResultSet:
        explain_sql = f"EXPLAIN (FORMAT JSON, BUFFERS, VERBOSE) {sql.strip().rstrip(';')}"
        return await self._raw_query(db_name=db_name or self._db_name, sql=explain_sql, args=[])

    def get_supported_metric_groups(self) -> list[str]:
        return ["health", "performance", "replication"]
