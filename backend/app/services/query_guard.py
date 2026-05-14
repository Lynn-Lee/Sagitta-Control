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


def _incomplete_statement_reason(prefix: str, tree: exp.Expression) -> str:
    if prefix in {"select", "with"} and isinstance(tree, exp.Select) and not tree.expressions:
        return "SQL 语法错误：SELECT 语句缺少查询字段"
    if prefix == "update" and isinstance(tree, exp.Update) and not tree.expressions:
        return "SQL 语法错误：UPDATE 语句缺少 SET 子句"
    if prefix == "insert" and isinstance(tree, exp.Insert):
        has_payload = (
            tree.args.get("expression")
            or tree.args.get("source")
            or tree.args.get("default")
        )
        if not has_payload:
            return "SQL 语法错误：INSERT 语句缺少 VALUES 或 SELECT 内容"
    if prefix == "delete" and isinstance(tree, exp.Delete) and not tree.this:
        return "SQL 语法错误：DELETE 语句缺少目标表"
    return ""


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
        try:
            parsed_statements = [
                statement
                for statement in sqlglot.parse(normalized, dialect=self.dialect)
                if statement is not None
            ]
        except sqlglot.errors.SqlglotError as exc:
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
        if prefix in {"show", "desc", "describe"}:
            return QueryGuardResult(
                True,
                statement_kind=kind,
                table_refs=_manual_table_ref(normalized, db_name, self.db_type),
                normalized_sql=normalized,
                needs_limit=False,
            )

        tree = parsed_statements[0]
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
            if re.match(r"^\s*explain\b.*\banalyze\b", normalized, re.I):
                return QueryGuardResult(
                    False,
                    "在线查询不允许 EXPLAIN ANALYZE 执行型解释计划",
                    prefix,
                    normalized_sql=normalized,
                )
            target_prefix = _first_word(parse_sql)
            incomplete_reason = _incomplete_statement_reason(target_prefix, tree)
            if incomplete_reason:
                return QueryGuardResult(
                    False,
                    incomplete_reason,
                    kind,
                    normalized_sql=normalized,
                )

        incomplete_reason = _incomplete_statement_reason(prefix, tree)
        if incomplete_reason:
            return QueryGuardResult(
                False,
                incomplete_reason,
                prefix,
                normalized_sql=normalized,
            )

        if prefix in WRITE_PREFIXES:
            return QueryGuardResult(
                False,
                f"在线查询不允许执行 {prefix.upper()} 操作",
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
        if re.search(r"\blimit\b", normalized, re.I):
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
