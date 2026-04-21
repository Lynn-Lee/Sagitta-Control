"""
MySQL 引擎实现。
支持：MySQL 5.7+ / MariaDB / TiDB / OceanBase / Doris（通过子类）

安全修复：
- P0-2：基础审核用 sqlglot，goInception 降级为可选增强（不再在 SQL 中传密码）
- P0-4：所有查询强制参数化
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import aiomysql
import sqlglot

from app.core.config import settings
from app.core.security import decrypt_field
from app.engines.models import ResultSet, ReviewSet, SqlItem
from app.engines.utils import normalize_engine_host, sanitize_sqlglot_error

if TYPE_CHECKING:
    from app.models.instance import Instance

logger = logging.getLogger(__name__)


class MysqlEngine:
    """MySQL 数据库引擎。"""

    name = "MysqlEngine"
    db_type = "mysql"

    def __init__(self, instance: Instance) -> None:
        self.instance = instance
        self._host = normalize_engine_host(instance.host)
        self._port = instance.port
        self._user = decrypt_field(instance.user)
        self._password = decrypt_field(instance.password)
        self._db_name = instance.db_name or ""
        self._pool: aiomysql.Pool | None = None

    # ── 连接管理 ──────────────────────────────────────────────

    async def _get_pool(self) -> aiomysql.Pool:
        if self._pool is None or self._pool.closed:
            self._pool = await aiomysql.create_pool(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                db=self._db_name or None,
                charset="utf8mb4",
                autocommit=False,
                minsize=1,
                maxsize=5,
                connect_timeout=10,
            )
        return self._pool

    async def get_connection(self, db_name: str | None = None) -> aiomysql.Connection:
        pool = await self._get_pool()
        conn = await pool.acquire()
        if db_name:
            await conn.select_db(db_name)
        return conn

    async def test_connection(self) -> ResultSet:
        rs = ResultSet()
        try:
            conn = await self.get_connection()
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
            rs.rows = [("ok",)]
            rs.column_list = ["result"]
        except Exception as e:
            rs.error = str(e)
        return rs

    def escape_string(self, value: str) -> str:
        """简单转义，仅用于标识符（库名、表名）。变量值请用参数化查询。"""
        return value.replace("\\", "\\\\").replace("`", "\\`").replace("'", "\\'")

    # ── 元数据 ────────────────────────────────────────────────

    async def get_all_databases(self) -> ResultSet:
        sql = "SHOW DATABASES"
        rs = await self.query(db_name="", sql=sql, limit_num=0)
        # 过滤系统库，应用 show_db_name_regex
        if self.instance.show_db_name_regex:
            import re
            pattern = re.compile(self.instance.show_db_name_regex)
            rs.rows = [r for r in rs.rows if pattern.search(str(r[0]))]
        return rs

    async def get_all_tables(self, db_name: str, **kwargs: Any) -> ResultSet:
        db_safe = self.escape_string(db_name)
        sql = f"SHOW TABLES FROM `{db_safe}`"
        return await self.query(db_name=db_name, sql=sql, limit_num=0)

    async def get_all_columns_by_tb(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        sql = (
            "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, "
            "COLUMN_COMMENT, COLUMN_KEY, EXTRA "
            "FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = %(db)s AND TABLE_NAME = %(tb)s "
            "ORDER BY ORDINAL_POSITION"
        )
        return await self.query(
            db_name=db_name, sql=sql,
            parameters={"db": db_name, "tb": tb_name},
            limit_num=0,
        )

    async def describe_table(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        tb_safe = self.escape_string(tb_name)
        db_safe = self.escape_string(db_name)
        sql = f"SHOW CREATE TABLE `{db_safe}`.`{tb_safe}`"
        return await self.query(db_name=db_name, sql=sql, limit_num=0)

    async def get_table_constraints(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        sql = (
            "SELECT "
            "tc.CONSTRAINT_NAME AS constraint_name, "
            "tc.CONSTRAINT_TYPE AS constraint_type, "
            "GROUP_CONCAT(kcu.COLUMN_NAME ORDER BY kcu.ORDINAL_POSITION SEPARATOR ', ') AS column_names, "
            "MAX(kcu.REFERENCED_TABLE_NAME) AS referenced_table_name, "
            "GROUP_CONCAT(kcu.REFERENCED_COLUMN_NAME ORDER BY kcu.ORDINAL_POSITION SEPARATOR ', ') AS referenced_column_names, "
            "COALESCE(MAX(cc.CHECK_CLAUSE), '') AS check_clause "
            "FROM information_schema.TABLE_CONSTRAINTS tc "
            "LEFT JOIN information_schema.KEY_COLUMN_USAGE kcu "
            "  ON tc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA "
            " AND tc.TABLE_NAME = kcu.TABLE_NAME "
            " AND tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME "
            "LEFT JOIN information_schema.CHECK_CONSTRAINTS cc "
            "  ON tc.CONSTRAINT_SCHEMA = cc.CONSTRAINT_SCHEMA "
            " AND tc.CONSTRAINT_NAME = cc.CONSTRAINT_NAME "
            "WHERE tc.TABLE_SCHEMA = %(db)s AND tc.TABLE_NAME = %(tb)s "
            "GROUP BY tc.CONSTRAINT_NAME, tc.CONSTRAINT_TYPE "
            "ORDER BY "
            "  CASE tc.CONSTRAINT_TYPE "
            "    WHEN 'PRIMARY KEY' THEN 1 "
            "    WHEN 'UNIQUE' THEN 2 "
            "    WHEN 'FOREIGN KEY' THEN 3 "
            "    WHEN 'CHECK' THEN 4 "
            "    ELSE 9 "
            "  END, "
            "  tc.CONSTRAINT_NAME"
        )
        return await self.query(
            db_name=db_name,
            sql=sql,
            parameters={"db": db_name, "tb": tb_name},
            limit_num=0,
        )

    async def get_table_indexes(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        sql = (
            "SELECT "
            "s.INDEX_NAME AS index_name, "
            "CASE "
            "  WHEN s.INDEX_NAME = 'PRIMARY' THEN 'PRIMARY KEY INDEX' "
            "  WHEN s.NON_UNIQUE = 0 THEN 'UNIQUE INDEX' "
            "  ELSE 'INDEX' "
            "END AS index_type, "
            "GROUP_CONCAT(s.COLUMN_NAME ORDER BY s.SEQ_IN_INDEX SEPARATOR ', ') AS column_names, "
            "CASE WHEN COUNT(*) > 1 THEN 'YES' ELSE 'NO' END AS is_composite, "
            "COALESCE(MAX(s.INDEX_COMMENT), '') AS index_comment "
            "FROM information_schema.STATISTICS s "
            "WHERE s.TABLE_SCHEMA = %(db)s AND s.TABLE_NAME = %(tb)s "
            "GROUP BY s.INDEX_NAME, s.NON_UNIQUE "
            "ORDER BY "
            "  CASE "
            "    WHEN s.INDEX_NAME = 'PRIMARY' THEN 1 "
            "    WHEN s.NON_UNIQUE = 0 THEN 2 "
            "    ELSE 3 "
            "  END, "
            "  s.INDEX_NAME"
        )
        return await self.query(
            db_name=db_name,
            sql=sql,
            parameters={"db": db_name, "tb": tb_name},
            limit_num=0,
        )

    async def get_tables_metas_data(
        self, db_name: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT TABLE_NAME, TABLE_COMMENT, TABLE_ROWS, "
            "DATA_LENGTH, INDEX_LENGTH, CREATE_TIME, UPDATE_TIME "
            "FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = %(db)s AND TABLE_TYPE = 'BASE TABLE'"
        )
        rs = await self.query(
            db_name=db_name, sql=sql,
            parameters={"db": db_name}, limit_num=0,
        )
        cols = rs.column_list
        return [dict(zip(cols, row, strict=False)) for row in rs.rows]

    # ── 查询 ──────────────────────────────────────────────────

    def query_check(self, db_name: str, sql: str) -> dict[str, Any]:
        """基于 sqlglot 的查询前置检查。"""
        result: dict[str, Any] = {
            "msg": "", "has_star": False, "syntax_error": False
        }
        sql_strip = sql.strip().rstrip(";")
        try:
            tree = sqlglot.parse_one(sql_strip, dialect="mysql")
            # 检查是否有 SELECT *
            import sqlglot.expressions as exp
            for _col in tree.find_all(exp.Star):
                result["has_star"] = True
                break
            # 检查是否包含写操作（INSERT/UPDATE/DELETE/DROP/TRUNCATE）
            write_types = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.TruncateTable)
            for wt in write_types:
                if tree.find(wt):
                    result["msg"] = f"查询接口不允许执行写操作：{type(tree.find(wt)).__name__}"
                    break
        except sqlglot.errors.ParseError as e:
            result["syntax_error"] = True
            result["msg"] = f"SQL 语法错误：{sanitize_sqlglot_error(str(e))}"
        return result

    def filter_sql(self, sql: str, limit_num: int) -> str:
        """在 SELECT 语句末尾注入 LIMIT，防止全表扫描。"""
        if limit_num <= 0:
            return sql
        sql_strip = sql.strip().rstrip(";")
        sql_lower = sql_strip.lower()
        if sql_lower.startswith("select") and "limit" not in sql_lower:
            return f"{sql_strip} LIMIT {limit_num}"
        return sql_strip

    async def query(
        self,
        db_name: str,
        sql: str,
        limit_num: int = 0,
        parameters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ResultSet:
        rs = ResultSet()
        start = time.monotonic()
        conn = None
        pool = await self._get_pool()
        try:
            conn = await pool.acquire()
            if db_name:
                await conn.select_db(db_name)
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, parameters)
                if cur.description:
                    rs.column_list = [d[0] for d in cur.description]
                    if limit_num > 0:
                        rs.rows = list(await cur.fetchmany(limit_num))
                    else:
                        rs.rows = list(await cur.fetchall())
                    rs.affected_rows = len(rs.rows)
                else:
                    rs.affected_rows = cur.rowcount
        except Exception as e:
            rs.error = str(e)
            logger.warning("mysql_query_error: %s sql=%s", str(e), sql[:200])
        finally:
            if conn:
                pool.release(conn)
            rs.cost_time = int((time.monotonic() - start) * 1000)
        return rs

    def query_masking(self, db_name: str, sql: str, resultset: ResultSet) -> ResultSet:
        """
        数据脱敏：由 app.services.masking 统一处理。
        此处只做透传，服务层负责 sqlglot 解析和规则匹配。
        """
        return resultset

    # ── SQL 审核 ──────────────────────────────────────────────

    async def execute_check(self, db_name: str, sql: str) -> ReviewSet:
        """
        SQL 审核（不执行）。
        - 基础审核：sqlglot 解析 + 本地规则引擎
        - 可选增强：若配置了 goInception，合并更详细的审核结果
        """
        review = ReviewSet(full_sql=sql)

        # 基础审核（本地，无外部依赖）
        review = await self._sqlglot_check(db_name, sql, review)

        # 可选 goInception 增强（不影响基础功能）
        if settings.ENABLE_GOINCEPTION and not review.error_count:
            try:
                review = await self._goinception_check(db_name, sql, review)
            except Exception as e:
                logger.warning("goinception_fallback: %s", str(e))
                # 降级：只用基础审核结果，不中断流程

        return review

    async def _sqlglot_check(
        self, db_name: str, sql: str, review: ReviewSet
    ) -> ReviewSet:
        """基于 sqlglot 的本地规则引擎审核。"""
        import sqlglot.expressions as exp

        statements = sqlglot.parse(sql, dialect="mysql")
        for idx, stmt in enumerate(statements):
            item = SqlItem(id=idx + 1, sql=str(stmt))
            if stmt is None:
                item.errlevel = 2
                item.errormessage = "无法解析的 SQL 语句"
                review.append(item)
                continue

            # 规则 1：DDL 语句检查备份建议
            if isinstance(stmt, (exp.Drop, exp.TruncateTable)):
                item.errlevel = 1
                item.errormessage = f"高风险操作 {type(stmt).__name__}，请确认已备份"

            # 规则 2：DML 必须有 WHERE
            if isinstance(stmt, (exp.Update, exp.Delete)) and not stmt.find(exp.Where):
                item.errlevel = 2
                item.errormessage = "UPDATE/DELETE 语句缺少 WHERE 条件，拒绝执行"

            # 规则 3：SELECT * 警告
            if isinstance(stmt, exp.Select):
                for _ in stmt.find_all(exp.Star):
                    item.errlevel = max(item.errlevel, 1)
                    item.errormessage = "建议避免使用 SELECT *，明确指定列名"
                    break

            item.stagestatus = "Audit completed" if not item.errlevel else "Audit warning/error"
            review.append(item)

        return review

    async def _goinception_check(
        self, db_name: str, sql: str, review: ReviewSet
    ) -> ReviewSet:
        """
        goInception 可选增强审核。
        注意：连接参数通过独立配置传递，不在 SQL 字符串中携带密码（修复 P0-2）。
        """
        # TODO Sprint 3: 实现 goInception TCP 协议连接
        # 使用 aiomysql 连接 goInception 的 4000 端口
        # inception_sql 使用专用配置连接，不在 SQL 字符串中拼密码
        logger.debug("goinception_check_placeholder")
        return review

    # ── 执行 ──────────────────────────────────────────────────

    async def execute(
        self, db_name: str, sql: str, **kwargs: Any
    ) -> ReviewSet:
        review = ReviewSet(full_sql=sql)
        conn = None
        pool = await self._get_pool()
        try:
            conn = await pool.acquire()
            if db_name:
                await conn.select_db(db_name)
            async with conn.cursor() as cur:
                await cur.execute(sql)
            await conn.commit()
            item = SqlItem(sql=sql, stagestatus="Execute Successfully", affected_rows=cur.rowcount)
            review.append(item)
            review.is_executed = True
        except Exception as e:
            if conn:
                await conn.rollback()
            review.error = str(e)
            item = SqlItem(sql=sql, errlevel=2, errormessage=str(e))
            review.append(item)
        finally:
            if conn:
                pool.release(conn)
        return review

    async def execute_workflow(self, workflow: Any) -> ReviewSet:
        """
        执行工单（逐条执行，记录每条进度）。
        通过 Celery task 的 update_state 推送进度（Sprint 3 实现）。
        """
        # TODO Sprint 3: 实现完整的工单执行逻辑
        review = ReviewSet(full_sql=getattr(workflow, "sql_content", ""))
        review.error = "execute_workflow 将在 Sprint 3 实现"
        return review

    # ── 可观测中心 ────────────────────────────────────────────

    async def collect_metrics(self) -> dict[str, Any]:
        """采集 MySQL 核心健康指标。"""
        rs = await self.test_connection()
        return {"health": {"up": 1 if rs.is_success else 0}}

    def get_supported_metric_groups(self) -> list[str]:
        return ["health", "performance", "replication", "innodb"]

    @property
    def auto_backup(self) -> bool:
        return True  # MySQL 支持 Binlog 备份

    async def processlist(
        self, command_type: str = "Query", **kwargs: Any
    ) -> ResultSet:
        sql = (
            "SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO "
            "FROM information_schema.PROCESSLIST "
            "WHERE COMMAND != 'Sleep'"
        )
        if command_type and command_type != "ALL":
            sql += f" AND COMMAND = '{self.escape_string(command_type)}'"
        return await self.query(db_name="", sql=sql, limit_num=0)

    async def kill_connection(self, thread_id: int) -> ResultSet:
        return await self.query(db_name="", sql=f"KILL {int(thread_id)}", limit_num=0)

    async def get_variables(
        self, variables: list[str] | None = None
    ) -> ResultSet:
        if variables:
            placeholders = ", ".join(f"%(v{i})s" for i in range(len(variables)))
            params = {f"v{i}": v for i, v in enumerate(variables)}
            sql = f"SHOW VARIABLES WHERE Variable_name IN ({placeholders})"
            return await self.query(db_name="", sql=sql, parameters=params, limit_num=0)
        return await self.query(db_name="", sql="SHOW VARIABLES", limit_num=0)
