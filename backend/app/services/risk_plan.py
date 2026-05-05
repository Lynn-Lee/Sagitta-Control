"""提交风险预案服务。

它刻意不做第二套 SQL 审核器，只在提交时为申请人和审核人生成简短预案，
用于风险提示和恢复准备。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.schemas.risk_plan import RiskPlan
from app.services.sql_analyzer import (
    BULK_INSERT_ROWS,
    RELATIONAL_DB_TYPES,
    SQLGLOT_DIALECTS,
    analyze_sql,
    is_relational_db_type,
)

__all__ = ["BULK_INSERT_ROWS", "RELATIONAL_DB_TYPES", "RiskPlanService", "SQLGLOT_DIALECTS"]

SEARCH_QUERY_DB_TYPES = {"elasticsearch", "opensearch"}


class RiskPlanService:
    @staticmethod
    def is_relational(db_type: str) -> bool:
        return is_relational_db_type(db_type)

    @staticmethod
    def is_privileged_workflow_sql(db_type: str, sql: str) -> bool:
        """判断 SQL 是否属于仅特权用户可提交的高危语句。"""
        if not RiskPlanService.is_relational(db_type):
            return False
        analysis = analyze_sql(db_type, "", sql)
        if analysis.parse_error is not None:
            return False

        for facts in analysis.statements:
            if facts.is_delete:
                return True
            if facts.is_update and not facts.has_where:
                return True
            if facts.is_ddl:
                return True
        return False

    @staticmethod
    def _unsupported(scope: str, db_type: str) -> RiskPlan:
        return RiskPlan(
            scope=scope,  # type: ignore[arg-type]
            level="low",
            summary=f"{db_type or '未知'} 暂不支持自动风险预案分析，请按业务流程补充人工说明。",
            suggestions=["请人工确认影响范围、备份方式和异常恢复路径。"],
        )

    @staticmethod
    def _plan(
        scope: str,
        level: str,
        summary: str,
        risks: list[str] | None = None,
        suggestions: list[str] | None = None,
    ) -> RiskPlan:
        high = level == "high"
        return RiskPlan(
            scope=scope,  # type: ignore[arg-type]
            level=level,  # type: ignore[arg-type]
            summary=summary,
            risks=risks or [],
            suggestions=suggestions or [],
            requires_confirmation=high,
            requires_manual_remark=high,
        )

    @staticmethod
    def build_workflow_plan(db_type: str, db_name: str, sql: str) -> RiskPlan:
        if not RiskPlanService.is_relational(db_type):
            return RiskPlanService._unsupported("workflow", db_type)

        risks: list[str] = []
        suggestions: list[str] = []
        level = "low"
        analysis = analyze_sql(db_type, db_name, sql)
        if analysis.parse_error is not None or not analysis.statements:
            return RiskPlanService._plan(
                "workflow",
                "high",
                "SQL 无法完成风险预案解析，需要人工确认变更风险。",
                ["SQL 解析失败，系统无法判断影响范围和恢复方式。"],
                ["请补充执行目的、影响范围、验证方式和异常恢复路径。"],
            )

        if analysis.has_multiple_statements:
            risks.append("包含多条 SQL，需逐条确认影响范围和执行顺序。")
            level = "medium"

        destructive_count = 0
        for facts in analysis.statements:
            table_name = facts.table_name

            if facts.is_delete:
                destructive_count += 1
                risks.append(f"DELETE 会删除 {table_name} 中符合条件的数据。")
                suggestions.append(
                    f"执行前备份完整受影响行：SELECT * FROM {table_name} WHERE <删除条件>;"
                )
                suggestions.append("回滚依赖备份数据或归档数据恢复，审批前请确认备份位置。")
                level = "high"
                if not facts.has_where:
                    risks.append("DELETE 未检测到 WHERE 条件，存在全表删除风险。")

            elif facts.is_update:
                destructive_count += 1
                col_text = ", ".join(facts.update_columns) if facts.update_columns else "被更新列"
                risks.append(f"UPDATE 会修改 {table_name} 的 {col_text}。")
                suggestions.append(
                    f"执行前备份主键和原值：SELECT <主键>, {col_text} FROM {table_name} WHERE <更新条件>;"
                )
                suggestions.append("回滚需要按主键将字段恢复为备份原值。")
                if not facts.has_where:
                    level = "high"
                    risks.append("UPDATE 未检测到 WHERE 条件，存在全表更新风险。")
                elif level != "high":
                    level = "medium"

            elif facts.is_insert:
                if facts.is_insert_select:
                    risks.append(
                        f"INSERT ... SELECT 会将查询结果写入 {table_name}，请确认来源数据范围。"
                    )
                    if level != "high":
                        level = "medium"
                elif facts.bulk_insert_rows >= BULK_INSERT_ROWS:
                    risks.append(f"INSERT 一次写入 {facts.bulk_insert_rows} 行，属于批量写入操作。")
                    if level != "high":
                        level = "medium"
                suggestions.append(
                    f"INSERT 回退通常依赖主键/唯一键删除新写入的 {table_name} 数据。"
                )

            elif facts.is_ddl:
                destructive_count += 1
                level = "high"
                risks.append("DDL 可能改变结构、锁表或造成不可直接回滚的影响。")
                suggestions.append("执行前请确认结构备份、应用兼容性和人工回退步骤。")

        if destructive_count > 1:
            level = "high"
            risks.append("包含多条破坏性 SQL，需申请人补充执行顺序和失败处置方式。")

        if level == "high":
            summary = "该 SQL 工单存在高风险变更，提交前必须补充风险/回滚说明。"
        elif level == "medium":
            summary = "该 SQL 工单存在数据变更风险，请确认备份和验证方式。"
        else:
            summary = "未发现明显高危变更，仍需按工单流程确认影响范围。"

        if not suggestions:
            suggestions.append("提交前请确认目标库、目标表和执行窗口。")

        return RiskPlanService._plan("workflow", level, summary, risks, suggestions)

    @staticmethod
    def build_query_privilege_plan(
        db_type: str,
        scope_type: str,
        db_name: str,
        table_name: str,
        valid_date: date,
        limit_num: int,
    ) -> RiskPlan:
        normalized_db_type = (db_type or "").lower()
        if not RiskPlanService.is_relational(db_type) and normalized_db_type not in SEARCH_QUERY_DB_TYPES:
            return RiskPlanService._unsupported("query_privilege", db_type)

        risks: list[str] = []
        suggestions: list[str] = []
        level = "low"

        days = (valid_date - date.today()).days
        if normalized_db_type in SEARCH_QUERY_DB_TYPES:
            if scope_type == "instance":
                level = "high"
                risks.append("申请集群级查询权限，访问范围覆盖该搜索集群下多个索引。")
            elif scope_type == "database":
                level = "high"
                risks.append(f"申请索引前缀级查询权限：{db_name}，访问范围覆盖匹配索引。")
            elif scope_type == "table":
                risks.append(f"申请索引级查询权限：{db_name}.{table_name}。")
        elif scope_type == "instance":
            level = "high"
            risks.append("申请实例级查询权限，访问范围覆盖该实例下多个数据库。")
        elif scope_type == "database":
            level = "high"
            risks.append(f"申请库级查询权限：{db_name}，访问范围覆盖该库下全部表。")
        elif scope_type == "table":
            risks.append(f"申请表级查询权限：{db_name}.{table_name}。")

        if days > 90:
            level = "high"
            risks.append("申请有效期超过 90 天，属于长期数据访问授权。")
        elif days > 30 and level != "high":
            level = "medium"
            risks.append("申请有效期超过 30 天，请确认必要性。")

        if limit_num >= 50000:
            level = "high"
            risks.append("单次查询行数上限较高，存在大批量读取或导出风险。")
        elif limit_num >= 10000 and level != "high":
            level = "medium"
            risks.append("单次查询行数上限较高，请确认业务需要。")

        suggestions.extend(
            [
                "申请理由应说明查询目的、数据范围和使用期限。",
                (
                    "审批时请关注授权粒度是否可缩小到具体索引。"
                    if normalized_db_type in SEARCH_QUERY_DB_TYPES
                    else "审批时请关注授权粒度是否可缩小到具体库或表。"
                ),
            ]
        )
        summary = (
            "查询权限申请风险较高，提交前必须补充访问用途和风险说明。"
            if level == "high"
            else "请确认查询权限范围、有效期和行数限制符合最小授权原则。"
        )
        return RiskPlanService._plan("query_privilege", level, summary, risks, suggestions)

    @staticmethod
    def build_archive_plan(
        db_type: str,
        archive_mode: str,
        source_db: str,
        source_table: str,
        condition: str,
        batch_size: int,
        estimated_rows: int | None = None,
        dest_db: str | None = None,
        dest_table: str | None = None,
    ) -> RiskPlan:
        if not RiskPlanService.is_relational(db_type):
            return RiskPlanService._unsupported("archive", db_type)

        count_unknown = estimated_rows is None
        count = int(estimated_rows or 0)
        risks: list[str] = []
        suggestions: list[str] = [
            f"执行前抽样校验：SELECT * FROM {source_table} WHERE {condition} LIMIT 20;",
            f"执行前确认影响行数：SELECT COUNT(*) FROM {source_table} WHERE {condition};",
        ]
        level = "low" if count == 0 and archive_mode != "purge" and batch_size < 5000 else "medium"

        if archive_mode == "purge":
            level = "high"
            risks.append("清理模式会从源表删除数据，完成后不能由平台自动撤销。")
            suggestions.append(
                f"执行前备份完整受影响行：SELECT * FROM {source_table} WHERE {condition};"
            )
        elif archive_mode == "dest":
            if level != "high" and count > 0:
                level = "medium"
            risks.append("归档模式会迁移数据并删除源表中已迁移记录。")
            suggestions.append(
                f"执行后校验目标表 {dest_db or source_db}.{dest_table or source_table} 行数和抽样数据。"
            )

        if count_unknown:
            level = "high"
            risks.append("系统无法可靠估算影响行数，需按高风险申请人工确认。")
        elif count >= 10000:
            level = "high"
            risks.append(f"预计影响 {count} 行，属于大批量数据变更。")
        elif count > 0:
            risks.append(f"预计影响 {count} 行。")

        if batch_size >= 5000:
            risks.append("批大小较大，可能增加锁等待或资源压力。")
            if level != "high":
                level = "medium"

        summary = (
            "该归档/清理申请风险较高，提交前必须补充恢复/验证说明。"
            if level == "high"
            else "请确认归档条件、批大小和执行前校验方式。"
        )
        return RiskPlanService._plan("archive", level, summary, risks, suggestions)

    @staticmethod
    def to_dict(plan: RiskPlan | dict[str, Any]) -> dict[str, Any]:
        if isinstance(plan, RiskPlan):
            return plan.model_dump()
        return plan
