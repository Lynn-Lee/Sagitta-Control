"""统一 SQL 审核规则层。

该服务用于 SQL 工单提交前的轻量审核，目标是覆盖多引擎公共风险规则。
它不依赖 goInception，也不替代数据库真实执行权限检查。
"""

from __future__ import annotations

from app.engines.models import ReviewSet, SqlItem
from app.engines.utils import sanitize_sqlglot_error
from app.services.sql_analyzer import BULK_INSERT_ROWS, SqlStatementFacts, analyze_sql


class SqlAuditService:
    """多引擎共享 SQL 审核规则。"""

    @staticmethod
    def audit(db_type: str, db_name: str, sql: str) -> ReviewSet:
        review = ReviewSet(full_sql=sql)
        analysis = analyze_sql(db_type, db_name, sql)
        if analysis.is_empty:
            review.append(
                SqlItem(
                    id=1,
                    sql="",
                    errlevel=2,
                    errormessage="SQL 不能为空",
                    stagestatus="Audit failed",
                )
            )
            return review

        if analysis.parse_error is not None:
            review.append(
                SqlItem(
                    id=1,
                    sql=analysis.raw_sql,
                    errlevel=2,
                    errormessage=f"SQL 解析失败：{sanitize_sqlglot_error(str(analysis.parse_error))}",
                    stagestatus="Audit failed",
                )
            )
            return review

        if not analysis.statements:
            review.append(
                SqlItem(
                    id=1,
                    sql=analysis.raw_sql,
                    errlevel=2,
                    errormessage="无法解析的 SQL 语句",
                    stagestatus="Audit failed",
                )
            )
            return review

        if analysis.has_multiple_statements:
            review.append(
                SqlItem(
                    id=0,
                    sql="",
                    errlevel=1,
                    errormessage="包含多条 SQL，请确认执行顺序、失败处理和回滚方案",
                    stagestatus="Audit warning",
                )
            )

        for facts in analysis.statements:
            item = SqlItem(id=facts.index, sql=facts.sql, stagestatus="Audit completed")
            SqlAuditService._apply_common_rules(item, facts, db_type)
            review.append(item)

        return review

    @staticmethod
    def _apply_common_rules(item: SqlItem, facts: SqlStatementFacts, db_type: str) -> None:
        if (facts.is_update or facts.is_delete) and not facts.has_where:
            SqlAuditService._set_error(item, "UPDATE/DELETE 语句缺少 WHERE 条件，拒绝执行")
            return

        if (
            facts.is_delete
            and (db_type or "").lower() == "starrocks"
            and "LIMIT" in item.sql.upper()
        ):
            SqlAuditService._set_error(
                item,
                "StarRocks DELETE 不按 MySQL DELETE ... LIMIT 分批执行，请使用明确 WHERE 条件",
            )
            return

        if facts.is_ddl:
            SqlAuditService._set_warning(
                item, "高风险 DDL 操作，请确认已备份、可回滚并避开业务高峰"
            )

        if facts.is_insert_select:
            SqlAuditService._set_warning(
                item, "INSERT ... SELECT 会批量写入查询结果，请确认来源范围"
            )
        elif facts.bulk_insert_rows >= BULK_INSERT_ROWS:
            SqlAuditService._set_warning(
                item,
                f"INSERT 一次写入 {facts.bulk_insert_rows} 行，请确认批量写入风险",
            )

        if facts.is_select and facts.has_select_star:
            SqlAuditService._set_warning(item, "建议避免使用 SELECT *，明确指定列名")

        if (db_type or "").lower() == "clickhouse" and (facts.is_update or facts.is_delete):
            SqlAuditService._set_warning(
                item, "ClickHouse 请使用 ALTER TABLE ... UPDATE/DELETE 语义"
            )

    @staticmethod
    def _set_warning(item: SqlItem, message: str) -> None:
        if item.errlevel < 1:
            item.errlevel = 1
            item.errormessage = message
            item.stagestatus = "Audit warning"

    @staticmethod
    def _set_error(item: SqlItem, message: str) -> None:
        item.errlevel = 2
        item.errormessage = message
        item.stagestatus = "Audit failed"
