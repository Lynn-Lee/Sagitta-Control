"""StarRocks 归档策略测试。"""

from app.services.archive import ARCHIVE_SUPPORT, build_batch_delete_sql, build_count_sql, check_support


def test_starrocks_supports_purge_only():
    purge_supported, purge_reason = check_support("starrocks", "purge")
    dest_supported, dest_reason = check_support("starrocks", "dest")

    assert purge_supported is True
    assert purge_reason == ""
    assert dest_supported is False
    assert "starrocks" in ARCHIVE_SUPPORT
    assert "不支持" in dest_reason


def test_starrocks_delete_does_not_use_mysql_limit_model():
    sql = build_batch_delete_sql("starrocks", "orders", "dt < '2024-01-01'", 1000)

    assert sql == "DELETE FROM `orders` WHERE dt < '2024-01-01'"
    assert "LIMIT" not in sql


def test_starrocks_count_uses_backtick_identifier():
    sql = build_count_sql("starrocks", "orders", "dt < '2024-01-01'")

    assert sql == "SELECT COUNT(*) FROM `orders` WHERE dt < '2024-01-01'"
