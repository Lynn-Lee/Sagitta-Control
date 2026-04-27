"""Read-only guards for the online query surface.

The query API is a read-only, no-side-effect execution surface. Different
engines need different syntax rules, but the router needs one fail-closed
contract.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import sqlglot
import sqlglot.expressions as exp

from app.engines.utils import sanitize_sqlglot_error
from app.services.masking import DIALECT_MAP


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
    def validate(self, sql: str, db_name: str) -> QueryGuardResult:
        ...

    def apply_limit(self, sql: str, limit_num: int, kind: str) -> str:
        ...


READ_PREFIXES = {"select", "with", "show", "desc", "describe", "explain"}
WRITE_PREFIXES = {
    "insert", "update", "delete", "create", "alter", "drop", "truncate",
    "replace", "merge", "call", "exec", "execute", "grant", "revoke",
    "set", "lock", "unlock", "copy", "do", "kill", "vacuum", "analyze",
    "optimize", "rename", "begin", "commit", "rollback", "use",
}

WRITE_EXPR_NAMES = (
    "Insert", "Update", "Delete", "Create", "Drop", "TruncateTable",
    "Merge", "Execute", "Command", "Copy", "Alter",
)
SIDE_EFFECT_FUNCTIONS = {
    "get_lock", "release_lock", "set_config", "pg_advisory_lock",
    "pg_advisory_xact_lock", "pg_terminate_backend", "pg_cancel_backend",
    "sleep", "benchmark",
}

UNSUPPORTED_ENGINES = {"doris", "cassandra", "elasticsearch", "opensearch"}


def _clean_sql(sql: str) -> str:
    return sql.strip().rstrip(";").strip()


def _first_word(sql: str) -> str:
    match = re.match(r"^\s*(?:--[^\n]*\n\s*|/\*.*?\*/\s*)*([a-zA-Z_]+)", sql, re.S)
    return match.group(1).lower() if match else ""


def _has_extra_statement(sql: str) -> bool:
    return ";" in sql.strip().rstrip(";")


def _cte_names(tree: exp.Expression) -> set[str]:
    names: set[str] = set()
    for cte in tree.find_all(exp.CTE):
        alias = cte.alias
        if alias:
            names.add(alias.lower())
    return names


def _table_refs_from_tree(tree: exp.Expression, db_name: str, db_type: str) -> list[dict[str, Any]]:
    default_schema = "" if db_type == "pgsql" else db_name
    cte_names = _cte_names(tree)
    seen: set[tuple[str, str]] = set()
    refs: list[dict[str, Any]] = []
    for tbl in tree.find_all(exp.Table):
        name = tbl.name
        if not name or name.lower() in cte_names:
            continue
        schema = tbl.db or default_schema
        key = (schema, name)
        if key not in seen:
            seen.add(key)
            refs.append({"schema": schema, "name": name})
    return refs


def _manual_table_ref(sql: str, db_name: str, db_type: str) -> list[dict[str, Any]]:
    default_schema = "" if db_type == "pgsql" else db_name
    patterns = [
        r"^\s*(?:desc|describe)\s+([`\"\[\]\w.]+)",
        r"^\s*show\s+create\s+table\s+([`\"\[\]\w.]+)",
        r"^\s*show\s+(?:full\s+)?columns\s+from\s+([`\"\[\]\w.]+)",
        r"^\s*show\s+index(?:es)?\s+from\s+([`\"\[\]\w.]+)",
    ]
    for pattern in patterns:
        match = re.match(pattern, sql, re.I)
        if not match:
            continue
        raw = match.group(1).strip("`\"[]")
        if "." in raw:
            schema, name = raw.rsplit(".", 1)
            return [{"schema": schema.strip("`\"[]"), "name": name.strip("`\"[]")}]
        return [{"schema": default_schema, "name": raw}]
    return []


def _strip_explain(sql: str) -> str:
    stripped = _clean_sql(sql)
    return re.sub(
        r"^\s*explain(?:\s+(?:analyze|costs|extended|formatted|verbose|plan|query\s+plan))*\s+",
        "",
        stripped,
        flags=re.I,
    ).strip()


class SqlQueryGuard:
    db_type: str

    def __init__(self, db_type: str) -> None:
        self.db_type = db_type
        self.dialect = DIALECT_MAP.get(db_type, "mysql")

    def validate(self, sql: str, db_name: str) -> QueryGuardResult:
        normalized = _clean_sql(sql)
        if not normalized:
            return QueryGuardResult(False, "SQL 不能为空")
        if _has_extra_statement(sql):
            return QueryGuardResult(False, "在线查询不允许执行多语句")

        prefix = _first_word(normalized)
        if prefix == "explain" and re.match(r"^\s*explain\b.*\banalyze\b", normalized, re.I):
            return QueryGuardResult(False, "在线查询不允许 EXPLAIN ANALYZE 执行型解释计划", prefix, normalized_sql=normalized)
        if prefix in WRITE_PREFIXES:
            return QueryGuardResult(False, f"在线查询不允许执行 {prefix.upper()} 操作", prefix, normalized_sql=normalized)
        if prefix not in READ_PREFIXES:
            return QueryGuardResult(False, f"在线查询只允许只读语句，不支持 {prefix.upper() or 'UNKNOWN'}", prefix, normalized_sql=normalized)

        parse_sql = _strip_explain(normalized) if prefix == "explain" else normalized
        kind = "with" if prefix == "with" else prefix
        if prefix in {"show", "desc", "describe"}:
            return QueryGuardResult(
                True,
                statement_kind=kind,
                table_refs=_manual_table_ref(normalized, db_name, self.db_type),
                normalized_sql=normalized,
                needs_limit=False,
            )

        try:
            tree = sqlglot.parse_one(parse_sql, dialect=self.dialect)
        except sqlglot.errors.ParseError as exc:
            if prefix == "explain":
                return QueryGuardResult(True, statement_kind=kind, normalized_sql=normalized)
            return QueryGuardResult(
                False,
                f"SQL 语法错误：{sanitize_sqlglot_error(str(exc))}",
                kind,
                normalized_sql=normalized,
            )

        if self._has_write_expression(tree):
            return QueryGuardResult(False, "在线查询不允许执行写操作", kind, normalized_sql=normalized)
        if self._has_select_into(tree):
            return QueryGuardResult(False, "在线查询不允许 SELECT INTO 写入操作", kind, normalized_sql=normalized)
        if self._has_locking_read(tree):
            return QueryGuardResult(False, "在线查询不允许锁定读语句", kind, normalized_sql=normalized)
        if self._has_side_effect_function(tree):
            return QueryGuardResult(False, "在线查询不允许调用可能产生副作用的函数", kind, normalized_sql=normalized)

        refs = _table_refs_from_tree(tree, db_name, self.db_type)
        return QueryGuardResult(
            True,
            statement_kind=kind,
            table_refs=refs,
            needs_limit=prefix in {"select", "with"},
            normalized_sql=normalized,
        )

    def _has_write_expression(self, tree: exp.Expression) -> bool:
        for name in WRITE_EXPR_NAMES:
            expr_type = getattr(exp, name, None)
            if expr_type is not None and tree.find(expr_type):
                return True
        return False

    def _has_select_into(self, tree: exp.Expression) -> bool:
        return any(bool(node.args.get("into")) for node in tree.find_all(exp.Select))

    def _has_locking_read(self, tree: exp.Expression) -> bool:
        return any(bool(node.args.get("locks")) for node in tree.find_all(exp.Select))

    def _has_side_effect_function(self, tree: exp.Expression) -> bool:
        for node in tree.walk():
            name = ""
            if isinstance(node, exp.Anonymous):
                name = str(node.this or "")
            elif isinstance(node, exp.Func):
                name = node.sql_name()
            if name and name.lower() in SIDE_EFFECT_FUNCTIONS:
                return True
        return False

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
                    return QueryGuardResult(False, "在线查询不允许 MongoDB aggregate 写入或执行代码阶段", "aggregate", normalized_sql=sql.strip())

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
    "get", "mget", "hget", "hgetall", "hkeys", "hvals", "lrange", "smembers",
    "scard", "zrange", "zrangebyscore", "zcard", "ttl", "pttl", "type",
    "exists", "strlen", "llen", "sismember", "zscore", "scan", "hscan",
    "sscan", "zscan", "info", "dbsize", "time", "ping", "object",
}


class RedisCommandGuard:
    def validate(self, sql: str, db_name: str) -> QueryGuardResult:
        parts = sql.strip().split()
        cmd = parts[0].lower() if parts else ""
        if cmd not in REDIS_READ_COMMANDS:
            return QueryGuardResult(False, f"在线查询不允许 Redis 命令 {cmd.upper() or 'UNKNOWN'}", cmd, normalized_sql=sql.strip())
        return QueryGuardResult(True, statement_kind=cmd, normalized_sql=sql.strip(), use_driver_limit=True)

    def apply_limit(self, sql: str, limit_num: int, kind: str) -> str:
        return sql.strip()


class UnsupportedQueryGuard:
    def __init__(self, db_type: str) -> None:
        self.db_type = db_type

    def validate(self, sql: str, db_name: str) -> QueryGuardResult:
        return QueryGuardResult(False, f"{self.db_type} 暂不支持在线查询执行", normalized_sql=sql.strip())

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
    if normalized == "mongo":
        return MongoQueryGuard()
    if normalized == "redis":
        return RedisCommandGuard()
    return UnsupportedQueryGuard(normalized)
