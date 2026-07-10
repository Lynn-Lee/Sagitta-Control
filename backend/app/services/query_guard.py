"""在线查询入口的只读防护。

查询 API 是只读、无副作用的执行入口。不同引擎有不同语法规则，
但路由层需要统一的 fail-close 契约。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import sqlglot
import sqlglot.expressions as exp

from app.engines.utils import sanitize_sqlglot_error
from app.services.masking import DIALECT_MAP
from app.services.sql_analyzer import (
    READ_PREFIXES,
    WRITE_PREFIXES,
)
from app.services.sql_analyzer import (
    clean_sql as _clean_sql,
)
from app.services.sql_analyzer import (
    first_word as _first_word,
)
from app.services.sql_analyzer import (
    has_extra_statement as _has_extra_statement,
)
from app.services.sql_analyzer import (
    has_locking_read as _has_locking_read,
)
from app.services.sql_analyzer import (
    has_select_into as _has_select_into,
)
from app.services.sql_analyzer import (
    has_side_effect_function as _has_side_effect_function,
)
from app.services.sql_analyzer import (
    has_write_expression as _has_write_expression,
)
from app.services.sql_analyzer import (
    manual_table_ref as _manual_table_ref,
)
from app.services.sql_analyzer import (
    strip_explain as _strip_explain,
)
from app.services.sql_analyzer import (
    table_refs_from_tree as _table_refs_from_tree,
)


@dataclass
class QueryGuardResult:
    allowed: bool
    reason: str = ""
    statement_kind: str = ""
    table_refs: list[dict[str, Any]] = field(default_factory=list)
    needs_limit: bool = False
    normalized_sql: str = ""
    use_driver_limit: bool = False


class QueryGuard(Protocol):
    def validate(self, sql: str, db_name: str) -> QueryGuardResult: ...

    def apply_limit(self, sql: str, limit_num: int, kind: str) -> str: ...


UNSUPPORTED_ENGINES: set[str] = set()


def _unknown_keyword_reason(prefix: str) -> str:
    return f"SQL 语法错误：无法识别关键字 {prefix.upper() or 'UNKNOWN'}"


def _read_command_syntax_reason(prefix: str, sql: str, tree: exp.Expression) -> str:
    if prefix == "show":
        if re.fullmatch(r"\s*show\s*", sql, re.I):
            return "SQL 语法错误：SHOW 语句缺少查询对象"
        if re.match(r"^\s*show\s+create\s+table\s*$", sql, re.I):
            return "SQL 语法错误：SHOW CREATE TABLE 语句缺少目标表"
        if re.match(r"^\s*show\s+(?:full\s+)?columns\s+from\s*$", sql, re.I):
            return "SQL 语法错误：SHOW COLUMNS 语句缺少目标表"
        if re.match(r"^\s*show\s+index(?:es)?\s+from\s*$", sql, re.I):
            return "SQL 语法错误：SHOW INDEX 语句缺少目标表"
        command_expr = tree.args.get("expression")
        if isinstance(tree, exp.Command) and not str(command_expr or "").strip():
            return "SQL 语法错误：SHOW 语句缺少查询对象"
    if prefix in {"desc", "describe"} and not re.match(r"^\s*(?:desc|describe)\s+\S+", sql, re.I):
        return "SQL 语法错误：DESCRIBE 语句缺少目标对象"
    return ""


def _statement_body(prefix: str, sql: str) -> str:
    return re.sub(rf"^\s*{re.escape(prefix)}\b", "", sql, count=1, flags=re.I).strip()


def _balanced_delimiters(sql: str) -> bool:
    stack: list[str] = []
    quote = ""
    escape = False
    pairs = {")": "(", "]": "["}
    for char in sql:
        if quote:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == quote:
                quote = ""
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char in {"(", "["}:
            stack.append(char)
        elif char in pairs and (not stack or stack.pop() != pairs[char]):
            return False
    return not quote and not stack


def _basic_syntax_reason(sql: str) -> str:
    if not _balanced_delimiters(sql):
        return "SQL 语法错误：括号或引号不匹配"
    if re.search(r",\s*\)", sql):
        return "SQL 语法错误：逗号后缺少表达式"
    if re.search(r"(?:=|<>|!=|<=|>=|<|>|\+|-|/|\|\||&&)\s*$", sql):
        return "SQL 语法错误：运算符后缺少表达式"
    return ""


def _manual_write_syntax_reason(prefix: str, sql: str) -> tuple[bool, str]:
    """Cover write statements sqlglot parses loosely or does not parse by dialect."""
    body = _statement_body(prefix, sql)
    if prefix == "replace":
        if not body or re.fullmatch(r"into", body, re.I):
            return True, "SQL 语法错误：REPLACE 语句缺少目标表"
        if not re.search(r"\b(?:values?|set|select)\b", body, re.I):
            return True, "SQL 语法错误：REPLACE 语句缺少 VALUES、SET 或 SELECT 内容"
        return True, ""
    if prefix == "grant":
        if not body:
            return True, "SQL 语法错误：GRANT 语句缺少授权内容"
        if not re.search(r"\bto\s+\S+", body, re.I):
            return True, "SQL 语法错误：GRANT 语句缺少授权对象"
        return True, ""
    if prefix == "revoke":
        if not body:
            return True, "SQL 语法错误：REVOKE 语句缺少回收内容"
        if not re.search(r"\bfrom\s+\S+", body, re.I):
            return True, "SQL 语法错误：REVOKE 语句缺少回收对象"
        return True, ""
    if prefix == "rename":
        if not body or re.fullmatch(r"table", body, re.I):
            return True, "SQL 语法错误：RENAME 语句缺少目标对象"
        if re.fullmatch(r"table\s+\S+", body, re.I):
            return True, "SQL 语法错误：RENAME 语句缺少新对象名"
        if not re.fullmatch(r"table\s+\S+\s+to\s+\S+(?:\s*,\s*\S+\s+to\s+\S+)*", body, re.I):
            return True, "SQL 语法错误：RENAME 语句格式不完整"
        return True, ""
    if prefix == "set":
        if not body:
            return True, "SQL 语法错误：SET 语句缺少配置项"
        if re.search(r"(?:=|\bto)\s*$", body, re.I):
            return True, "SQL 语法错误：SET 语句缺少配置值"
        if not re.search(r"[=]", body) and not re.fullmatch(r"\S+\s+(?:to\s+)?\S+.*", body, re.I):
            return True, "SQL 语法错误：SET 语句缺少配置值"
        return True, ""
    if prefix in {"call", "exec", "execute"}:
        if not body:
            return True, f"SQL 语法错误：{prefix.upper()} 语句缺少调用目标"
        return True, ""
    if prefix == "use":
        if not body:
            return True, "SQL 语法错误：USE 语句缺少目标数据库"
        return True, ""
    if prefix == "lock":
        if not body:
            return True, "SQL 语法错误：LOCK 语句缺少目标对象"
        if re.fullmatch(r"tables?\s+\S+", body, re.I):
            return True, "SQL 语法错误：LOCK TABLES 语句缺少锁模式"
        return True, ""
    if prefix == "unlock":
        if not body:
            return True, "SQL 语法错误：UNLOCK 语句缺少目标对象"
        return True, ""
    if prefix == "copy":
        if not body or not re.search(r"\b(?:to|from)\b\s+\S+", body, re.I):
            return True, "SQL 语法错误：COPY 语句缺少 TO/FROM 目标"
        return True, ""
    return False, ""


def _has_like_property(tree: exp.Expression) -> bool:
    properties = tree.args.get("properties")
    expressions = getattr(properties, "expressions", None) or []
    return any(isinstance(item, exp.LikeProperty) for item in expressions)


def _ast_error_reason(tree: exp.Expression) -> str:
    for node in tree.walk():
        current = node[0] if isinstance(node, tuple) else node
        if not isinstance(current, exp.Expression):
            continue
        errors = current.error_messages()
        if errors:
            return f"SQL 语义错误：{sanitize_sqlglot_error(errors[0])}"
    return ""


def _create_table_semantic_reason(tree: exp.Create) -> str:
    kind = str(tree.args.get("kind") or "").upper()
    if kind != "TABLE" or not isinstance(tree.this, exp.Schema):
        return ""
    for item in tree.this.expressions:
        if isinstance(item, exp.ColumnDef):
            if not item.args.get("kind"):
                return "SQL 语义错误：CREATE TABLE 列定义缺少数据类型"
            continue
        if isinstance(
            item,
            (
                exp.PrimaryKey,
                exp.UniqueColumnConstraint,
                exp.ForeignKey,
                exp.CheckColumnConstraint,
            ),
        ):
            continue
        return "SQL 语义错误：CREATE TABLE 表结构定义不合法"
    return ""


def _alter_table_semantic_reason(tree: exp.Expression) -> str:
    if tree.__class__.__name__ not in {"Alter", "AlterTable"}:
        return ""
    for action in tree.args.get("actions") or []:
        if isinstance(action, exp.ColumnDef) and not action.args.get("kind"):
            return "SQL 语义错误：ALTER TABLE 列定义缺少数据类型"
        if isinstance(action, exp.Identifier):
            return "SQL 语义错误：ALTER TABLE 变更动作不完整"
    return ""


def _insert_semantic_reason(tree: exp.Insert) -> str:
    expression = tree.args.get("expression")
    if not isinstance(expression, exp.Values):
        return ""
    rows = [row for row in expression.expressions if isinstance(row, exp.Tuple)]
    if not rows:
        return ""
    row_lengths = [len(row.expressions) for row in rows]
    if len(set(row_lengths)) > 1:
        return "SQL 语义错误：INSERT 每行 VALUES 数量不一致"
    target = tree.this
    columns = target.expressions if isinstance(target, exp.Schema) else []
    if columns and row_lengths[0] != len(columns):
        return "SQL 语义错误：INSERT 列数量和值数量不一致"
    return ""


def _semantic_validation_reason(prefix: str, tree: exp.Expression) -> str:
    ast_reason = _ast_error_reason(tree)
    if ast_reason:
        return ast_reason
    if prefix == "insert" and isinstance(tree, exp.Insert):
        return _insert_semantic_reason(tree)
    if prefix == "create" and isinstance(tree, exp.Create):
        return _create_table_semantic_reason(tree)
    if prefix == "alter":
        return _alter_table_semantic_reason(tree)
    return ""


def _write_policy_reason(prefix: str, tree: exp.Expression) -> str:
    if prefix == "update" and isinstance(tree, exp.Update) and not tree.args.get("where"):
        return "在线查询不允许执行 UPDATE 操作：缺少 WHERE 条件"
    if prefix == "delete" and isinstance(tree, exp.Delete) and not tree.args.get("where"):
        return "在线查询不允许执行 DELETE 操作：缺少 WHERE 条件"
    if prefix == "insert" and isinstance(tree, exp.Insert) and isinstance(
        tree.args.get("expression"), exp.Select
    ):
        return "在线查询不允许执行 INSERT ... SELECT 写入操作"
    return f"在线查询不允许执行 {prefix.upper()} 操作"


def _syntax_validation_reason(prefix: str, sql: str, tree: exp.Expression) -> str:
    if prefix in {"select", "with"} and isinstance(tree, exp.Select) and not tree.expressions:
        return "SQL 语法错误：SELECT 语句缺少查询字段"
    if prefix == "update" and isinstance(tree, exp.Update):
        if not tree.this:
            return "SQL 语法错误：UPDATE 语句缺少目标表"
        if not tree.expressions:
            return "SQL 语法错误：UPDATE 语句缺少 SET 子句"
    if prefix == "insert" and isinstance(tree, exp.Insert):
        if not tree.this:
            return "SQL 语法错误：INSERT 语句缺少目标表"
        has_payload = (
            tree.args.get("expression")
            or tree.args.get("source")
            or tree.args.get("default")
        )
        if not has_payload:
            return "SQL 语法错误：INSERT 语句缺少 VALUES 或 SELECT 内容"
    if prefix == "replace" and isinstance(tree, exp.Command):
        _, reason = _manual_write_syntax_reason(prefix, sql)
        if reason:
            return reason
    if prefix == "delete" and isinstance(tree, exp.Delete) and not tree.this:
        return "SQL 语法错误：DELETE 语句缺少目标表"
    if prefix == "create" and isinstance(tree, exp.Create):
        kind = str(tree.args.get("kind") or "").upper()
        if not tree.this:
            return "SQL 语法错误：CREATE 语句缺少目标对象"
        if kind == "TABLE":
            has_column_defs = isinstance(tree.this, exp.Schema) and bool(tree.this.expressions)
            if not has_column_defs and not tree.args.get("expression") and not _has_like_property(tree):
                return "SQL 语法错误：CREATE TABLE 语句缺少列定义或 AS/LIKE 子句"
        if kind == "VIEW" and not tree.args.get("expression"):
            return "SQL 语法错误：CREATE VIEW 语句缺少 AS SELECT 子句"
        if kind in {"FUNCTION", "PROCEDURE"} and not (
            tree.args.get("expression") or tree.args.get("begin") or tree.args.get("end")
        ):
            return f"SQL 语法错误：CREATE {kind} 语句缺少定义体"
    if prefix == "drop" and isinstance(tree, exp.Drop) and not tree.this:
        return "SQL 语法错误：DROP 语句缺少目标对象"
    if prefix in {"create", "drop"} and isinstance(tree, exp.Command):
        command_expr = str(tree.args.get("expression") or "").strip()
        if not command_expr or re.fullmatch(
            r"(?:database|function|index|procedure|role|schema|sequence|table|trigger|user|view)",
            command_expr,
            re.I,
        ):
            return f"SQL 语法错误：{prefix.upper()} 语句缺少目标对象"
        if prefix == "create" and re.fullmatch(r"(?:function|procedure|trigger)\s+\S+", command_expr, re.I):
            return "SQL 语法错误：CREATE 语句缺少定义体"
    if prefix == "alter" and tree.__class__.__name__ in {"Alter", "AlterTable"}:
        if not tree.this:
            return "SQL 语法错误：ALTER 语句缺少目标对象"
        if not tree.args.get("actions"):
            return "SQL 语法错误：ALTER 语句缺少变更动作"
    if prefix == "alter" and isinstance(tree, exp.Command):
        command_expr = str(tree.args.get("expression") or "").strip()
        if not command_expr:
            return "SQL 语法错误：ALTER 语句缺少目标对象"
        if re.fullmatch(r"table", command_expr, re.I):
            return "SQL 语法错误：ALTER 语句缺少目标对象"
        if re.fullmatch(r"(?:\w+\s+)?\S+", command_expr, re.I):
            return "SQL 语法错误：ALTER 语句缺少变更动作"
        if re.fullmatch(r"(?:table\s+)?\S+\s+rename(?:\s+to)?", command_expr, re.I):
            return "SQL 语法错误：ALTER RENAME 语句缺少新对象名"
        if re.fullmatch(r"table\s+\S+\s+add(?:\s+column)?", command_expr, re.I):
            return "SQL 语法错误：ALTER ADD COLUMN 语句缺少列定义"
    if prefix == "truncate" and isinstance(tree, exp.TruncateTable) and not tree.expressions:
        return "SQL 语法错误：TRUNCATE 语句缺少目标表"
    if prefix == "truncate" and re.fullmatch(r"\s*truncate(?:\s+table)?\s*", sql, re.I):
        return "SQL 语法错误：TRUNCATE 语句缺少目标表"
    if prefix == "rename" and re.fullmatch(r"\s*rename(?:\s+table)?\s*", sql, re.I):
        return "SQL 语法错误：RENAME 语句缺少目标对象"
    if prefix in {"grant", "revoke", "set", "call", "exec", "execute", "use", "lock", "unlock", "copy"}:
        _, reason = _manual_write_syntax_reason(prefix, sql)
        if reason:
            return reason
    if prefix in WRITE_PREFIXES and isinstance(tree, exp.Column) and tree.name.lower() == prefix:
        return f"SQL 语法错误：{prefix.upper()} 语句不完整"
    if prefix == "alter" and re.match(r"^\s*alter\s+table\s+\S+\s*$", sql, re.I):
        return "SQL 语法错误：ALTER 语句缺少变更动作"
    return ""


def _ast_inject_limit(normalized: str, limit_num: int, dialect: str) -> str | None:
    """用 AST 精确注入行数上限。

    仅识别顶层查询的 LIMIT，避免字符串字面量或注释中的 ``limit`` 被正则误判为
    已存在上限；已有顶层 LIMIT 时原样返回，否则按目标方言生成带 LIMIT 的 SQL。
    解析或生成失败返回 None，由调用方回退到保守字符串追加。
    """
    try:
        tree = sqlglot.parse_one(normalized, dialect=dialect)
    except sqlglot.errors.SqlglotError:
        return None
    if tree is None:
        return None
    if tree.args.get("limit") is not None:
        return normalized
    try:
        return tree.limit(limit_num).sql(dialect=dialect)
    except Exception:
        return None


def _ast_has_limit(normalized: str, dialect: str) -> bool | None:
    """仅判断顶层查询是否已有 LIMIT；解析失败返回 None。

    用于不便整体重写 SQL 的方言（如 Elasticsearch，索引名转义与原文差异敏感），
    在保持原始 SQL 文本的前提下修正 ``\\blimit\\b`` 正则的误判。
    """
    try:
        tree = sqlglot.parse_one(normalized, dialect=dialect)
    except sqlglot.errors.SqlglotError:
        return None
    if tree is None:
        return None
    return tree.args.get("limit") is not None


class SqlQueryGuard:
    db_type: str

    def __init__(self, db_type: str) -> None:
        self.db_type = db_type
        self.dialect = DIALECT_MAP.get(db_type, "mysql")

    def validate(self, sql: str, db_name: str) -> QueryGuardResult:
        normalized = _clean_sql(sql)
        if not normalized:
            return QueryGuardResult(False, "SQL 不能为空")

        prefix = _first_word(normalized)
        basic_syntax_reason = _basic_syntax_reason(normalized)
        if basic_syntax_reason:
            return QueryGuardResult(
                False,
                basic_syntax_reason,
                prefix,
                normalized_sql=normalized,
            )
        try:
            parsed_statements = [
                statement
                for statement in sqlglot.parse(normalized, dialect=self.dialect)
                if statement is not None
            ]
        except sqlglot.errors.SqlglotError as exc:
            has_manual_syntax, manual_reason = _manual_write_syntax_reason(prefix, normalized)
            if has_manual_syntax:
                if manual_reason:
                    return QueryGuardResult(
                        False,
                        manual_reason,
                        prefix,
                        normalized_sql=normalized,
                    )
                return QueryGuardResult(
                    False,
                    f"在线查询不允许执行 {prefix.upper()} 操作",
                    prefix,
                    normalized_sql=normalized,
                )
            return QueryGuardResult(
                False,
                f"SQL 语法错误：{sanitize_sqlglot_error(str(exc))}",
                prefix,
                normalized_sql=normalized,
            )
        if not parsed_statements:
            return QueryGuardResult(
                False,
                "SQL 语法错误：无法解析 SQL 语句",
                prefix,
                normalized_sql=normalized,
            )
        if len(parsed_statements) > 1:
            return QueryGuardResult(False, "在线查询不允许执行多语句", normalized_sql=normalized)

        kind = "with" if prefix == "with" else prefix
        tree = parsed_statements[0]
        if prefix not in READ_PREFIXES and prefix not in WRITE_PREFIXES:
            return QueryGuardResult(
                False,
                _unknown_keyword_reason(prefix),
                prefix,
                normalized_sql=normalized,
            )
        read_command_reason = _read_command_syntax_reason(prefix, normalized, tree)
        if read_command_reason:
            return QueryGuardResult(
                False,
                read_command_reason,
                prefix,
                normalized_sql=normalized,
            )
        if prefix in {"show", "desc", "describe"}:
            return QueryGuardResult(
                True,
                statement_kind=kind,
                table_refs=_manual_table_ref(normalized, db_name, self.db_type),
                normalized_sql=normalized,
                needs_limit=False,
            )

        if prefix == "explain":
            parse_sql = _strip_explain(normalized)
            try:
                explain_statements = [
                    statement
                    for statement in sqlglot.parse(parse_sql, dialect=self.dialect)
                    if statement is not None
                ]
            except sqlglot.errors.SqlglotError as exc:
                return QueryGuardResult(
                    False,
                    f"SQL 语法错误：{sanitize_sqlglot_error(str(exc))}",
                    kind,
                    normalized_sql=normalized,
                )
            if not explain_statements:
                return QueryGuardResult(
                    False,
                    "SQL 语法错误：无法解析 EXPLAIN 目标语句",
                    kind,
                    normalized_sql=normalized,
                )
            if len(explain_statements) > 1:
                return QueryGuardResult(False, "在线查询不允许执行多语句", normalized_sql=normalized)
            tree = explain_statements[0]
            target_prefix = _first_word(parse_sql)
            if target_prefix not in READ_PREFIXES and target_prefix not in WRITE_PREFIXES:
                return QueryGuardResult(
                    False,
                    _unknown_keyword_reason(target_prefix),
                    kind,
                    normalized_sql=normalized,
                )
            read_command_reason = _read_command_syntax_reason(target_prefix, parse_sql, tree)
            if read_command_reason:
                return QueryGuardResult(
                    False,
                    read_command_reason,
                    kind,
                    normalized_sql=normalized,
                )
            syntax_reason = _syntax_validation_reason(target_prefix, parse_sql, tree)
            if syntax_reason:
                return QueryGuardResult(
                    False,
                    syntax_reason,
                    kind,
                    normalized_sql=normalized,
                )
            semantic_reason = _semantic_validation_reason(target_prefix, tree)
            if semantic_reason:
                return QueryGuardResult(
                    False,
                    semantic_reason,
                    kind,
                    normalized_sql=normalized,
                )
            if re.match(r"^\s*explain\b.*\banalyze\b", normalized, re.I):
                return QueryGuardResult(
                    False,
                    "在线查询不允许 EXPLAIN ANALYZE 执行型解释计划",
                    prefix,
                    normalized_sql=normalized,
                )

        syntax_reason = _syntax_validation_reason(prefix, normalized, tree)
        if syntax_reason:
            return QueryGuardResult(
                False,
                syntax_reason,
                prefix,
                normalized_sql=normalized,
            )
        semantic_reason = _semantic_validation_reason(prefix, tree)
        if semantic_reason:
            return QueryGuardResult(
                False,
                semantic_reason,
                prefix,
                normalized_sql=normalized,
            )

        if prefix in WRITE_PREFIXES:
            return QueryGuardResult(
                False,
                _write_policy_reason(prefix, tree),
                prefix,
                normalized_sql=normalized,
            )
        if prefix not in READ_PREFIXES:
            return QueryGuardResult(
                False,
                f"在线查询不允许执行 {prefix.upper() or 'UNKNOWN'} 操作",
                prefix,
                normalized_sql=normalized,
            )

        if _has_write_expression(tree):
            return QueryGuardResult(
                False, "在线查询不允许执行写操作", kind, normalized_sql=normalized
            )
        if _has_select_into(tree):
            return QueryGuardResult(
                False, "在线查询不允许 SELECT INTO 写入操作", kind, normalized_sql=normalized
            )
        if _has_locking_read(tree):
            return QueryGuardResult(
                False, "在线查询不允许锁定读语句", kind, normalized_sql=normalized
            )
        if _has_side_effect_function(tree):
            return QueryGuardResult(
                False, "在线查询不允许调用可能产生副作用的函数", kind, normalized_sql=normalized
            )

        refs = _table_refs_from_tree(tree, db_name, self.db_type)
        return QueryGuardResult(
            True,
            statement_kind=kind,
            table_refs=refs,
            needs_limit=prefix in {"select", "with"},
            normalized_sql=normalized,
        )

    def apply_limit(self, sql: str, limit_num: int, kind: str) -> str:
        normalized = _clean_sql(sql)
        if limit_num <= 0 or kind not in {"select", "with"}:
            return normalized
        injected = _ast_inject_limit(normalized, limit_num, self.dialect)
        if injected is not None:
            return injected
        # AST 不可用时回退保守字符串追加（validate 已确保可解析，正常不会走到这里）
        if re.search(r"\blimit\b", normalized, re.I):
            return normalized
        return f"{normalized} LIMIT {limit_num}"


class StarRocksQueryGuard(SqlQueryGuard):
    def __init__(self, db_type: str = "starrocks") -> None:
        super().__init__(db_type)


class PgsqlQueryGuard(SqlQueryGuard):
    def __init__(self, db_type: str = "pgsql") -> None:
        super().__init__(db_type)


class OracleQueryGuard(SqlQueryGuard):
    def __init__(self, db_type: str = "oracle") -> None:
        super().__init__(db_type)

    def apply_limit(self, sql: str, limit_num: int, kind: str) -> str:
        normalized = _clean_sql(sql)
        if limit_num <= 0 or kind not in {"select", "with"}:
            return normalized
        return f"SELECT * FROM ({normalized}) WHERE ROWNUM <= {limit_num}"


class MssqlQueryGuard(SqlQueryGuard):
    def __init__(self, db_type: str = "mssql") -> None:
        super().__init__(db_type)

    def apply_limit(self, sql: str, limit_num: int, kind: str) -> str:
        normalized = _clean_sql(sql)
        if limit_num <= 0 or kind not in {"select", "with"}:
            return normalized
        if re.search(r"\btop\s*\(?\d+", normalized, re.I):
            return normalized
        return f"SELECT TOP ({limit_num}) * FROM ({normalized}) AS sagitta_subq"


class ClickHouseQueryGuard(SqlQueryGuard):
    def __init__(self, db_type: str = "clickhouse") -> None:
        super().__init__(db_type)


class DorisQueryGuard(SqlQueryGuard):
    def __init__(self, db_type: str = "doris") -> None:
        super().__init__(db_type)


class ElasticsearchQueryGuard(SqlQueryGuard):
    def __init__(self, db_type: str = "elasticsearch") -> None:
        super().__init__(db_type)

    def apply_limit(self, sql: str, limit_num: int, kind: str) -> str:
        normalized = _clean_sql(sql)
        if limit_num <= 0 or kind not in {"select", "with"}:
            return normalized
        has_limit = _ast_has_limit(normalized, self.dialect)
        if has_limit is None:
            # 解析失败回退正则判断，保持 ES 原始 SQL 文本不被重写
            has_limit = bool(re.search(r"\blimit\b", normalized, re.I))
        if has_limit:
            return normalized
        return f"{normalized} LIMIT {limit_num}"


class CassandraQueryGuard:
    db_type = "cassandra"

    def validate(self, sql: str, db_name: str) -> QueryGuardResult:
        normalized = _clean_sql(sql)
        if not normalized:
            return QueryGuardResult(False, "CQL 不能为空")
        if _has_extra_statement(sql):
            return QueryGuardResult(False, "在线查询不允许执行多语句", normalized_sql=normalized)

        prefix = _first_word(normalized)
        if prefix in WRITE_PREFIXES:
            return QueryGuardResult(
                False,
                f"在线查询不允许执行 {prefix.upper()} 操作",
                prefix,
                normalized_sql=normalized,
            )
        if prefix != "select":
            current = prefix.upper() or "UNKNOWN"
            reason = (
                f"Cassandra 在线查询只允许 SELECT，不支持 {current} 语句"
                if prefix in READ_PREFIXES
                else f"CQL 语法错误：无法识别关键字 {current}"
            )
            return QueryGuardResult(
                False,
                reason,
                prefix,
                normalized_sql=normalized,
            )
        if re.search(r"(?is)\bselect\b.+\binto\b", normalized):
            return QueryGuardResult(False, "在线查询不允许 SELECT INTO 写入操作", prefix)
        if re.search(r"(?is)\bfor\s+update\b", normalized):
            return QueryGuardResult(False, "在线查询不允许锁定读", prefix)
        table_refs = self._table_refs(normalized, db_name)
        if not table_refs:
            return QueryGuardResult(
                False,
                "Cassandra SELECT 必须包含 FROM 表引用",
                prefix,
                normalized_sql=normalized,
            )
        return QueryGuardResult(
            True,
            statement_kind=prefix,
            table_refs=table_refs,
            normalized_sql=normalized,
            needs_limit=not re.search(r"\blimit\b", normalized, re.I),
        )

    def apply_limit(self, sql: str, limit_num: int, kind: str) -> str:
        sql_strip = sql.strip().rstrip(";")
        if (
            kind == "select"
            and limit_num > 0
            and not re.search(r"\blimit\b", sql_strip, re.I)
        ):
            return f"{sql_strip} LIMIT {int(limit_num)}"
        return sql_strip

    @staticmethod
    def _table_refs(sql: str, db_name: str) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for match in re.finditer(
            r"(?is)\bfrom\s+([a-zA-Z_][\w]*)(?:\.([a-zA-Z_][\w]*))?",
            sql,
        ):
            schema = match.group(1)
            table = match.group(2)
            refs.append({"schema": schema if table else db_name, "name": table or schema})
        return refs

class MongoQueryGuard:
    FORBIDDEN_AGG_STAGES = {"$out", "$merge", "$function", "$accumulator"}

    def validate(self, sql: str, db_name: str) -> QueryGuardResult:
        from app.engines.mongo import MongoEngine

        parser = MongoEngine._parse_mongo_query
        try:
            parsed = parser(None, sql)  # type: ignore[misc]
        except ValueError as exc:
            return QueryGuardResult(False, str(exc), normalized_sql=sql.strip())

        if parsed["type"] == "aggregate":
            for stage in parsed.get("pipeline", []):
                if isinstance(stage, dict) and self.FORBIDDEN_AGG_STAGES & set(stage.keys()):
                    return QueryGuardResult(
                        False,
                        "在线查询不允许 MongoDB aggregate 写入或执行代码阶段",
                        "aggregate",
                        normalized_sql=sql.strip(),
                    )

        return QueryGuardResult(
            True,
            statement_kind=parsed["type"],
            table_refs=[{"schema": db_name, "name": parsed["collection"]}],
            normalized_sql=sql.strip(),
            needs_limit=parsed["type"] in {"find", "aggregate"},
            use_driver_limit=True,
        )

    def apply_limit(self, sql: str, limit_num: int, kind: str) -> str:
        return sql.strip()


REDIS_READ_COMMANDS = {
    "get",
    "mget",
    "hget",
    "hgetall",
    "hkeys",
    "hvals",
    "lrange",
    "smembers",
    "scard",
    "zrange",
    "zrangebyscore",
    "zcard",
    "ttl",
    "pttl",
    "type",
    "exists",
    "strlen",
    "llen",
    "sismember",
    "zscore",
    "scan",
    "hscan",
    "sscan",
    "zscan",
    "info",
    "dbsize",
    "time",
    "ping",
    "object",
}


class RedisCommandGuard:
    def validate(self, sql: str, db_name: str) -> QueryGuardResult:
        parts = sql.strip().split()
        cmd = parts[0].lower() if parts else ""
        if cmd not in REDIS_READ_COMMANDS:
            return QueryGuardResult(
                False,
                f"在线查询不允许 Redis 命令 {cmd.upper() or 'UNKNOWN'}",
                cmd,
                normalized_sql=sql.strip(),
            )
        return QueryGuardResult(
            True, statement_kind=cmd, normalized_sql=sql.strip(), use_driver_limit=True
        )

    def apply_limit(self, sql: str, limit_num: int, kind: str) -> str:
        return sql.strip()


class UnsupportedQueryGuard:
    def __init__(self, db_type: str) -> None:
        self.db_type = db_type

    def validate(self, sql: str, db_name: str) -> QueryGuardResult:
        return QueryGuardResult(
            False, f"{self.db_type} 暂不支持在线查询执行", normalized_sql=sql.strip()
        )

    def apply_limit(self, sql: str, limit_num: int, kind: str) -> str:
        return sql.strip()


def get_query_guard(db_type: str) -> QueryGuard:
    normalized = db_type.lower()
    if normalized in UNSUPPORTED_ENGINES:
        return UnsupportedQueryGuard(normalized)
    if normalized in {"mysql", "tidb"}:
        return SqlQueryGuard(normalized)
    if normalized == "starrocks":
        return StarRocksQueryGuard()
    if normalized == "pgsql":
        return PgsqlQueryGuard()
    if normalized == "oracle":
        return OracleQueryGuard()
    if normalized == "mssql":
        return MssqlQueryGuard()
    if normalized == "clickhouse":
        return ClickHouseQueryGuard()
    if normalized == "doris":
        return DorisQueryGuard()
    if normalized in {"elasticsearch", "opensearch"}:
        return ElasticsearchQueryGuard(normalized)
    if normalized == "cassandra":
        return CassandraQueryGuard()
    if normalized == "mongo":
        return MongoQueryGuard()
    if normalized == "redis":
        return RedisCommandGuard()
    return UnsupportedQueryGuard(normalized)
