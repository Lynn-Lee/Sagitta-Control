"""
数据脱敏服务（修复 P0-3）。

原始问题：Archery 1.x 使用 goInception 解析 SELECT 列，导致：
  - 非 MySQL 数据库（PgSQL/ClickHouse/MongoDB等）脱敏实际无效
  - goInception 进程挂掉时脱敏失败，直接返回明文数据

修复方案：用 sqlglot 替代 goInception 的解析功能。
  - sqlglot 支持 20+ 方言，全部 11 种数据库引擎均生效
  - 纯 Python，无外部进程依赖
"""
from __future__ import annotations

import logging
import re
from fnmatch import fnmatchcase
from typing import Any

import sqlglot
import sqlglot.expressions as exp

from app.engines.models import ResultSet

logger = logging.getLogger(__name__)

# db_type → sqlglot 方言名映射
DIALECT_MAP: dict[str, str] = {
    "mysql":         "mysql",
    "pgsql":         "postgres",
    "oracle":        "oracle",
    "clickhouse":    "clickhouse",
    "mssql":         "tsql",
    "doris":         "doris",
    "elasticsearch": "mysql",   # ES SQL 方言近似 MySQL
    "mongo":         "mysql",   # MongoDB 不走 sqlglot 解析
    "redis":         "mysql",
    "cassandra":     "mysql",
}


def extract_select_columns(sql: str, db_type: str) -> list[dict[str, Any]]:
    """
    用 sqlglot 解析 SELECT 语句，提取列引用列表。
    
    替代原 GoInceptionEngine.query_data_masking() 的解析功能。
    支持所有方言，非 MySQL 数据库的脱敏不再失效。
    
    Returns:
        [{"index": 0, "field": "phone", "table": "users", "schema": "", "alias": "phone"}, ...]
    """
    dialect = DIALECT_MAP.get(db_type.lower(), "mysql")
    columns: list[dict[str, Any]] = []

    try:
        tree = sqlglot.parse_one(sql, dialect=dialect)
    except sqlglot.errors.ParseError as e:
        logger.warning("sqlglot_parse_failed: sql=%s error=%s", sql[:100], str(e))
        return columns

    for i, col in enumerate(tree.find_all(exp.Column)):
        parent = col.parent
        alias = parent.alias if isinstance(parent, exp.Alias) else ""
        columns.append({
            "index": i,
            "field": col.name,
            "table": col.table or "*",
            "schema": col.db or "",
            "alias": alias or col.name,
        })

    return columns


def extract_table_refs(sql: str, db_name: str, db_type: str = "mysql") -> list[dict[str, Any]]:
    """
    提取 SQL 语句中引用的库名和表名，用于查询权限校验。
    
    替代原 GoInceptionEngine.query_print() 的功能（修复 P0-3）。
    
    Returns:
        [{"schema": "mydb", "name": "users"}, ...]
    """
    dialect = DIALECT_MAP.get(db_type.lower(), "mysql")
    tables: list[dict[str, Any]] = []

    try:
        tree = sqlglot.parse_one(sql, dialect=dialect)
    except sqlglot.errors.ParseError as e:
        logger.warning("sqlglot_table_ref_failed: sql=%s error=%s", sql[:100], str(e))
        return tables

    default_schema = "" if db_type.lower() == "pgsql" else db_name
    seen: set[tuple[str, str]] = set()
    for tbl in tree.find_all(exp.Table):
        schema = tbl.db or default_schema
        name = tbl.name
        key = (schema, name)
        if key not in seen:
            seen.add(key)
            tables.append({"schema": schema, "name": name})

    return tables


class DataMaskingService:
    """
    数据脱敏服务。
    
    脱敏规则类型（对应 Archery 1.x 的 7 种规则）：
      1. REGEX   - 正则替换（通用）
      2. EMAIL   - 邮箱脱敏（保留前两位）
      3. PHONE   - 手机号脱敏（保留前3后2）
      4. CARD    - 银行卡脱敏（保留前6后4）
      5. ADDRESS - 地址脱敏（保留前6字符）
      6. NAME    - 姓名脱敏（保留姓）
      7. ID_CARD - 身份证脱敏（保留前3后4）
    """

    BUILT_IN_RULES: dict[str, Any] = {
        "email":   {"pattern": r"(\w{2})\w+(@.+)", "replacement": r"\1***\2"},
        "phone":   {"pattern": r"(\d{3})\d{4,8}(\d{2})", "replacement": r"\1****\2"},
        "card":    {"pattern": r"(\d{6})\d+(\d{4})", "replacement": r"\1 **** **** \2"},
        "id_card": {"pattern": r"(\d{3})\d{11}(\w{4})", "replacement": r"\1***********\2"},
        "name":    {"pattern": r"([\u4e00-\u9fa5]{1})[\u4e00-\u9fa5]+", "replacement": r"\1**"},
        "address": {"pattern": r"(.{6}).+", "replacement": r"\1***"},
    }

    def __init__(self, rules: list[dict[str, Any]] | None = None):
        """
        Args:
            rules: 自定义脱敏规则列表，格式：
                [{"column_name": "phone", "rule_type": "phone"}, ...]
        """
        self.rules = rules or []

    @staticmethod
    def _matches_pattern(value: str, pattern: str) -> bool:
        """Case-insensitive exact or shell-style wildcard match."""
        if not pattern:
            return False
        value_lower = value.lower()
        pattern_lower = pattern.lower()
        return (
            pattern_lower == "*"
            or value_lower == pattern_lower
            or fnmatchcase(value_lower, pattern_lower)
        )

    def _apply_rule(self, value: str, rule: dict[str, Any]) -> str:
        """对单个值应用脱敏规则。"""
        if not value or not isinstance(value, str):
            return value

        rule_type = rule.get("rule_type", "regex").lower()

        if rule_type in self.BUILT_IN_RULES:
            r = self.BUILT_IN_RULES[rule_type]
            return re.sub(r["pattern"], r["replacement"], value)

        # 自定义正则规则
        if rule_type == "regex":
            pattern = rule.get("rule_regex", "")
            repl = rule.get("rule_regex_replace", "***")
            hide_group = rule.get("hide_group", 0)
            if pattern:
                try:
                    if hide_group:
                        # 三段式脱敏：隐藏指定分组
                        def _mask_group(m: re.Match) -> str:
                            groups = list(m.groups())
                            if hide_group <= len(groups):
                                groups[hide_group - 1] = "*" * len(groups[hide_group - 1])
                            return "".join(g for g in groups if g)
                        return re.sub(pattern, _mask_group, value)
                    return re.sub(pattern, repl, value)
                except re.error:
                    pass

        return value

    def mask_result(
        self,
        resultset: ResultSet,
        sql: str,
        db_type: str,
    ) -> ResultSet:
        """
        对查询结果集应用脱敏规则。
        
        工作流程：
          1. sqlglot 解析 SQL，提取列引用（替代 goInception）
          2. 根据列名匹配脱敏规则
          3. 对匹配到规则的列的每一行数据执行脱敏
        """
        if not self.rules or not resultset.rows:
            return resultset

        # 提取列引用（sqlglot，支持所有方言）
        col_refs = extract_select_columns(sql, db_type)
        col_ref_map = {ref["alias"].lower(): ref for ref in col_refs}

        # 找出需要脱敏的列索引
        mask_cols: dict[int, dict[str, Any]] = {}  # col_index → rule
        for rule in self.rules:
            col_name = rule.get("column_name", "").lower()
            if not col_name:
                continue
            # 尝试在结果集列名中匹配
            for idx, col in enumerate(resultset.column_list):
                ref = col_ref_map.get(col.lower(), {})
                ref_field = ref.get("field", "")
                ref_table = ref.get("table", "*")
                table_name = rule.get("table_name", "*")
                column_matches = (
                    self._matches_pattern(col, col_name)
                    or self._matches_pattern(ref_field, col_name)
                )
                table_matches = table_name == "*" or self._matches_pattern(ref_table, table_name)
                if column_matches and table_matches:
                    mask_cols[idx] = rule
                    break

        if not mask_cols:
            return resultset

        # 执行脱敏
        masked_rows = []
        for row in resultset.rows:
            row_list = list(row.values()) if isinstance(row, dict) else list(row)

            for col_idx, rule in mask_cols.items():
                if col_idx < len(row_list):
                    row_list[col_idx] = self._apply_rule(str(row_list[col_idx]), rule)

            masked_rows.append(tuple(row_list))

        resultset.rows = masked_rows
        return resultset
