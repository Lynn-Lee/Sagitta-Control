"""Shared SQL analysis primitives.

This module extracts SQL facts only. It intentionally avoids product decisions
such as whether to block, warn, or require an approval remark.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import sqlglot
import sqlglot.expressions as exp

RELATIONAL_DB_TYPES = {
    "mysql",
    "tidb",
    "pgsql",
    "postgres",
    "postgresql",
    "oracle",
    "mssql",
    "clickhouse",
    "starrocks",
    "doris",
}

SQLGLOT_DIALECTS = {
    "mysql": "mysql",
    "tidb": "mysql",
    "doris": "mysql",
    "starrocks": "mysql",
    "pgsql": "postgres",
    "postgres": "postgres",
    "postgresql": "postgres",
    "oracle": "oracle",
    "mssql": "tsql",
    "clickhouse": "clickhouse",
}

BULK_INSERT_ROWS = 100

READ_PREFIXES = {"select", "with", "show", "desc", "describe", "explain"}
WRITE_PREFIXES = {
    "insert",
    "update",
    "delete",
    "create",
    "alter",
    "drop",
    "truncate",
    "replace",
    "merge",
    "call",
    "exec",
    "execute",
    "grant",
    "revoke",
    "set",
    "lock",
    "unlock",
    "copy",
    "do",
    "kill",
    "vacuum",
    "analyze",
    "optimize",
    "rename",
    "begin",
    "commit",
    "rollback",
    "use",
}

WRITE_EXPR_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Create",
    "Drop",
    "TruncateTable",
    "Merge",
    "Execute",
    "Command",
    "Copy",
    "Alter",
)
SIDE_EFFECT_FUNCTIONS = {
    "get_lock",
    "release_lock",
    "set_config",
    "pg_advisory_lock",
    "pg_advisory_xact_lock",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "sleep",
    "benchmark",
}


@dataclass(frozen=True)
class SqlStatementFacts:
    index: int
    sql: str
    expression: exp.Expression
    command_name: str = ""
    table_name: str = "目标表"
    table_refs: list[dict[str, Any]] = field(default_factory=list)
    update_columns: list[str] = field(default_factory=list)
    is_select: bool = False
    is_insert: bool = False
    is_update: bool = False
    is_delete: bool = False
    is_ddl: bool = False
    is_insert_select: bool = False
    bulk_insert_rows: int = 0
    has_where: bool = False
    has_select_star: bool = False
    has_write_expression: bool = False
    has_select_into: bool = False
    has_locking_read: bool = False
    has_side_effect_function: bool = False


@dataclass(frozen=True)
class SqlAnalysis:
    db_type: str
    db_name: str
    dialect: str
    raw_sql: str
    statements: list[SqlStatementFacts] = field(default_factory=list)
    parse_error: Exception | None = None
    is_empty: bool = False

    @property
    def has_multiple_statements(self) -> bool:
        return len(self.statements) > 1


def is_relational_db_type(db_type: str) -> bool:
    return (db_type or "").lower() in RELATIONAL_DB_TYPES


def dialect_for_db_type(db_type: str) -> str:
    return SQLGLOT_DIALECTS.get((db_type or "").lower(), "mysql")


def clean_sql(sql: str) -> str:
    return sql.strip().rstrip(";").strip()


def first_word(sql: str) -> str:
    match = re.match(r"^\s*(?:--[^\n]*\n\s*|/\*.*?\*/\s*)*([a-zA-Z_]+)", sql, re.S)
    return match.group(1).lower() if match else ""


def has_extra_statement(sql: str) -> bool:
    return ";" in sql.strip().rstrip(";")


def strip_explain(sql: str) -> str:
    stripped = clean_sql(sql)
    return re.sub(
        r"^\s*explain(?:\s+(?:analyze|costs|extended|formatted|verbose|plan|query\s+plan))*\s+",
        "",
        stripped,
        flags=re.I,
    ).strip()


def cte_names(tree: exp.Expression) -> set[str]:
    names: set[str] = set()
    for cte in tree.find_all(exp.CTE):
        alias = cte.alias
        if alias:
            names.add(alias.lower())
    return names


def table_refs_from_tree(tree: exp.Expression, db_name: str, db_type: str) -> list[dict[str, Any]]:
    default_schema = "" if db_type == "pgsql" else db_name
    local_cte_names = cte_names(tree)
    seen: set[tuple[str, str]] = set()
    refs: list[dict[str, Any]] = []
    for tbl in tree.find_all(exp.Table):
        name = tbl.name
        if not name or name.lower() in local_cte_names:
            continue
        schema = tbl.db or default_schema
        key = (schema, name)
        if key not in seen:
            seen.add(key)
            refs.append({"schema": schema, "name": name})
    return refs


def manual_table_ref(sql: str, db_name: str, db_type: str) -> list[dict[str, Any]]:
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
        raw = match.group(1).strip('`"[]')
        if "." in raw:
            schema, name = raw.rsplit(".", 1)
            return [{"schema": schema.strip('`"[]'), "name": name.strip('`"[]')}]
        return [{"schema": default_schema, "name": raw}]
    return []


def has_write_expression(tree: exp.Expression) -> bool:
    for name in WRITE_EXPR_NAMES:
        expr_type = getattr(exp, name, None)
        if expr_type is not None and tree.find(expr_type):
            return True
    return False


def has_select_into(tree: exp.Expression) -> bool:
    return any(bool(node.args.get("into")) for node in tree.find_all(exp.Select))


def has_locking_read(tree: exp.Expression) -> bool:
    return any(bool(node.args.get("locks")) for node in tree.find_all(exp.Select))


def has_side_effect_function(tree: exp.Expression) -> bool:
    for node in tree.walk():
        current = node[0] if isinstance(node, tuple) else node
        name = ""
        if isinstance(current, exp.Anonymous):
            name = str(current.this or "")
        elif isinstance(current, exp.Func):
            name = current.sql_name()
        if name and name.lower() in SIDE_EFFECT_FUNCTIONS:
            return True
    return False


def _ddl_types() -> tuple[type[exp.Expression], ...]:
    return tuple(
        item
        for item in (
            exp.Create,
            exp.Drop,
            getattr(exp, "Alter", None),
            getattr(exp, "AlterTable", None),
            getattr(exp, "TruncateTable", None),
        )
        if item is not None
    )


def _table_name(tree: exp.Expression) -> str:
    table = tree.find(exp.Table)
    return table.name if table else "目标表"


def _update_columns(tree: exp.Expression) -> list[str]:
    columns = [eq.left.name for eq in tree.find_all(exp.EQ) if isinstance(eq.left, exp.Column)]
    return list(dict.fromkeys(columns))


def _statement_facts(
    index: int, stmt: exp.Expression, db_type: str, db_name: str
) -> SqlStatementFacts:
    command_name = str(getattr(stmt, "this", "") or "").upper()
    expression = stmt.args.get("expression")
    is_insert = isinstance(stmt, exp.Insert)
    is_ddl = isinstance(stmt, _ddl_types()) or command_name in {"RENAME", "TRUNCATE"}
    bulk_insert_rows = len(expression.expressions) if isinstance(expression, exp.Values) else 0
    return SqlStatementFacts(
        index=index,
        sql=str(stmt),
        expression=stmt,
        command_name=command_name,
        table_name=_table_name(stmt),
        table_refs=table_refs_from_tree(stmt, db_name, db_type),
        update_columns=_update_columns(stmt),
        is_select=isinstance(stmt, exp.Select),
        is_insert=is_insert,
        is_update=isinstance(stmt, exp.Update),
        is_delete=isinstance(stmt, exp.Delete),
        is_ddl=is_ddl,
        is_insert_select=is_insert and isinstance(expression, exp.Select),
        bulk_insert_rows=bulk_insert_rows,
        has_where=stmt.find(exp.Where) is not None,
        has_select_star=any(True for _ in stmt.find_all(exp.Star)),
        has_write_expression=has_write_expression(stmt),
        has_select_into=has_select_into(stmt),
        has_locking_read=has_locking_read(stmt),
        has_side_effect_function=has_side_effect_function(stmt),
    )


def analyze_sql(db_type: str, db_name: str, sql: str) -> SqlAnalysis:
    raw = (sql or "").strip()
    dialect = dialect_for_db_type(db_type)
    if not raw:
        return SqlAnalysis(
            db_type=db_type, db_name=db_name, dialect=dialect, raw_sql=raw, is_empty=True
        )

    try:
        parsed = sqlglot.parse(raw, dialect=dialect)
    except Exception as exc:  # noqa: BLE001 - callers convert parser errors into domain results.
        return SqlAnalysis(
            db_type=db_type, db_name=db_name, dialect=dialect, raw_sql=raw, parse_error=exc
        )

    statements = [
        _statement_facts(index, stmt, (db_type or "").lower(), db_name)
        for index, stmt in enumerate((stmt for stmt in parsed if stmt is not None), start=1)
    ]
    return SqlAnalysis(
        db_type=db_type, db_name=db_name, dialect=dialect, raw_sql=raw, statements=statements
    )
