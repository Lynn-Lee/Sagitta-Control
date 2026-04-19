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
import time
from typing import TYPE_CHECKING, Any

import oracledb
import sqlglot
import sqlglot.expressions as exp

from app.core.security import decrypt_field
from app.engines.models import ResultSet, ReviewSet, SqlItem
from app.engines.utils import normalize_engine_host, sanitize_sqlglot_error

if TYPE_CHECKING:
    from app.models.instance import Instance

logger = logging.getLogger(__name__)


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
            rs.error = str(e)
            logger.warning("oracle_query_error: %s", str(e))
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

    async def get_all_columns_by_tb(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        sql = """
        SELECT column_name, data_type, nullable, data_default
        FROM all_tab_columns
        WHERE owner = :owner AND table_name = :table_name
        ORDER BY column_id
        """
        return await asyncio.to_thread(
            self._run_query_sync,
            sql,
            {"owner": db_name.upper(), "table_name": tb_name.upper()},
        )

    async def describe_table(self, db_name: str, tb_name: str, **kwargs: Any) -> ResultSet:
        return await self.get_all_columns_by_tb(db_name, tb_name, **kwargs)

    async def get_tables_metas_data(self, db_name: str, **kwargs: Any) -> list[dict[str, Any]]:
        rs = await self.get_all_tables(db_name)
        if not rs.is_success:
            return []
        return [{"table_name": row[0]} for row in rs.rows]

    async def get_table_constraints(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        sql = """
        SELECT
            c.constraint_name,
            c.constraint_type,
            LISTAGG(cols.column_name, ', ') WITHIN GROUP (ORDER BY cols.position) AS column_names,
            MAX(ref.table_name) AS referenced_table_name,
            LISTAGG(ref_cols.column_name, ', ') WITHIN GROUP (ORDER BY ref_cols.position) AS referenced_column_names
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
        rs = await asyncio.to_thread(
            self._run_query_sync,
            sql,
            {"owner": db_name.upper(), "table_name": tb_name.upper()},
        )
        if rs.is_success:
            mapping = {"P": "PRIMARY KEY", "U": "UNIQUE", "R": "FOREIGN KEY", "C": "CHECK"}
            normalized_rows = []
            for row in rs.rows:
                row_dict = dict(zip(rs.column_list, row, strict=False))
                row_dict["CONSTRAINT_TYPE"] = mapping.get(
                    str(row_dict.get("CONSTRAINT_TYPE", "")),
                    str(row_dict.get("CONSTRAINT_TYPE", "")),
                )
                normalized_rows.append(row_dict)
            rs.rows = normalized_rows
        return rs

    async def get_table_indexes(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        sql = """
        SELECT
            i.index_name,
            CASE
              WHEN i.uniqueness = 'UNIQUE' THEN 'UNIQUE INDEX'
              ELSE 'INDEX'
            END AS index_type,
            LISTAGG(cols.column_name, ', ') WITHIN GROUP (ORDER BY cols.column_position) AS column_names,
            CASE
              WHEN COUNT(*) > 1 THEN 'YES'
              ELSE 'NO'
            END AS is_composite,
            COALESCE(MAX(com.comments), '') AS index_comment
        FROM all_indexes i
        JOIN all_ind_columns cols
          ON i.owner = cols.index_owner
         AND i.index_name = cols.index_name
         AND i.table_name = cols.table_name
        LEFT JOIN all_ind_comments com
          ON i.owner = com.index_owner
         AND i.index_name = com.index_name
         AND i.table_name = com.table_name
        WHERE i.table_owner = :owner
          AND i.table_name = :table_name
        GROUP BY i.index_name, i.uniqueness
        ORDER BY
          CASE
            WHEN i.index_name LIKE 'PK_%' THEN 1
            WHEN i.uniqueness = 'UNIQUE' THEN 2
            ELSE 3
          END,
          i.index_name
        """
        return await asyncio.to_thread(
            self._run_query_sync,
            sql,
            {"owner": db_name.upper(), "table_name": tb_name.upper()},
        )

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

    async def collect_metrics(self) -> dict:
        return {"health": {"up": 1 if (await self.test_connection()).is_success else 0}}

    def get_supported_metric_groups(self) -> list[str]:
        return ["health"]
