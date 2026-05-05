from app.services.sql_analyzer import BULK_INSERT_ROWS, analyze_sql


def test_analyzer_marks_update_without_where():
    analysis = analyze_sql("mysql", "app", "UPDATE users SET status = 0")

    assert analysis.parse_error is None
    assert len(analysis.statements) == 1
    facts = analysis.statements[0]
    assert facts.is_update is True
    assert facts.has_where is False
    assert facts.table_name == "users"
    assert facts.update_columns == ["status"]


def test_analyzer_table_refs_skip_cte_alias():
    analysis = analyze_sql(
        "mysql",
        "analytics",
        "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent",
    )

    facts = analysis.statements[0]
    assert facts.is_select is True
    assert facts.has_select_star is True
    assert facts.table_refs == [{"schema": "analytics", "name": "orders"}]


def test_analyzer_insert_select_and_bulk_values():
    insert_select = analyze_sql(
        "mysql",
        "app",
        "INSERT INTO audit_users SELECT * FROM users WHERE status = 0",
    ).statements[0]
    values_sql = "INSERT INTO users (id) VALUES " + ", ".join(
        f"({idx})" for idx in range(BULK_INSERT_ROWS)
    )
    bulk_insert = analyze_sql("mysql", "app", values_sql).statements[0]

    assert insert_select.is_insert is True
    assert insert_select.is_insert_select is True
    assert bulk_insert.bulk_insert_rows == BULK_INSERT_ROWS


def test_analyzer_ddl_and_delete_facts():
    ddl = analyze_sql("mysql", "app", "TRUNCATE TABLE users").statements[0]
    delete = analyze_sql("mysql", "app", "DELETE FROM users WHERE id = 1").statements[0]

    assert ddl.is_ddl is True
    assert delete.is_delete is True
    assert delete.has_where is True


def test_analyzer_detects_query_guard_side_effect_facts():
    select_into = analyze_sql("pgsql", "app", "SELECT * INTO users_copy FROM users").statements[0]
    locking_read = analyze_sql("pgsql", "app", "SELECT * FROM users FOR UPDATE").statements[0]
    side_effect = analyze_sql("pgsql", "app", "SELECT pg_advisory_lock(1)").statements[0]

    assert select_into.has_select_into is True
    assert locking_read.has_locking_read is True
    assert side_effect.has_side_effect_function is True


def test_analyzer_returns_parse_error():
    analysis = analyze_sql("mysql", "app", "SELECT FROM")

    assert analysis.parse_error is not None
    assert analysis.statements == []
