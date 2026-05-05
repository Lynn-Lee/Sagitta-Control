from app.services.sql_audit import SqlAuditService


def _levels(review):
    return [item.errlevel for item in review.rows]


def test_audit_rejects_update_without_where_across_dialects():
    for db_type in ["mysql", "tidb", "pgsql", "oracle", "mssql", "starrocks"]:
        review = SqlAuditService.audit(db_type, "app", "UPDATE users SET status = 0")

        assert review.error_count == 1
        assert any("WHERE" in item.errormessage for item in review.rows)


def test_audit_warns_for_high_risk_ddl():
    review = SqlAuditService.audit("pgsql", "app", "DROP TABLE users")

    assert review.warning_count == 1
    assert review.error_count == 0
    assert "高风险 DDL" in review.rows[0].errormessage


def test_audit_warns_for_select_star():
    review = SqlAuditService.audit("mysql", "app", "SELECT * FROM users")

    assert review.warning_count == 1
    assert review.error_count == 0
    assert "SELECT *" in review.rows[0].errormessage


def test_audit_warns_for_multi_statement_sequence():
    review = SqlAuditService.audit(
        "mysql",
        "app",
        "INSERT INTO users (id) VALUES (1); INSERT INTO users (id) VALUES (2);",
    )

    assert 1 in _levels(review)
    assert any("多条 SQL" in item.errormessage for item in review.rows)


def test_audit_warns_for_insert_select():
    review = SqlAuditService.audit(
        "mysql",
        "app",
        "INSERT INTO archive_users SELECT * FROM users WHERE status = 0",
    )

    assert review.warning_count >= 1
    assert any("INSERT ... SELECT" in item.errormessage for item in review.rows)


def test_audit_rejects_starrocks_delete_limit():
    review = SqlAuditService.audit(
        "starrocks",
        "app",
        "DELETE FROM users WHERE status = 0 LIMIT 100",
    )

    assert review.error_count == 1
    assert "StarRocks DELETE" in review.rows[0].errormessage


def test_audit_returns_parse_error_as_review_item():
    review = SqlAuditService.audit("mysql", "app", "SELECT FROM")

    assert review.error_count == 1
    assert "SQL 解析失败" in review.rows[0].errormessage


def test_audit_rejects_comment_only_sql():
    review = SqlAuditService.audit("mysql", "app", "-- only comment")

    assert review.error_count == 1
    assert "无法解析" in review.rows[0].errormessage
