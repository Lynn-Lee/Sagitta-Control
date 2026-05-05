"""Doris 归档策略测试。"""

from app.services.archive import (
    ARCHIVE_SUPPORT,
    build_batch_delete_sql,
    build_count_sql,
    check_support,
)


def test_doris_supports_purge_only():
    purge_supported, purge_reason = check_support("doris", "purge")
    dest_supported, dest_reason = check_support("doris", "dest")

    assert purge_supported is True
    assert purge_reason == ""
    assert dest_supported is False
    assert "doris" in ARCHIVE_SUPPORT
    assert "purge" in dest_reason


def test_doris_delete_uses_where_delete_without_mysql_limit():
    sql = build_batch_delete_sql("doris", "orders", "dt < '2024-01-01'", 1000)

    assert sql == "DELETE FROM `orders` WHERE dt < '2024-01-01'"
    assert "LIMIT" not in sql


def test_doris_count_uses_backtick_identifier():
    sql = build_count_sql("doris", "orders", "dt < '2024-01-01'")

    assert sql == "SELECT COUNT(*) FROM `orders` WHERE dt < '2024-01-01'"
