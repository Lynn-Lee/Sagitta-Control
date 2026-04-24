"""
数据脱敏服务单元测试。
验证 sqlglot 替代 goInception 的解析功能（修复 P0-3）。
"""

from app.engines.models import ResultSet
from app.services.masking import (
    DataMaskingService,
    extract_select_columns,
    extract_table_refs,
)


class TestExtractSelectColumns:
    """测试 sqlglot 列引用提取（替代 goInception）。"""

    def test_simple_select(self):
        cols = extract_select_columns("SELECT id, name, phone FROM users", "mysql")
        assert len(cols) == 3
        fields = [c["field"] for c in cols]
        assert "id" in fields
        assert "name" in fields
        assert "phone" in fields

    def test_select_with_table_prefix(self):
        cols = extract_select_columns("SELECT u.id, u.phone FROM users u", "mysql")
        phone_col = next((c for c in cols if c["field"] == "phone"), None)
        assert phone_col is not None
        assert phone_col["table"] == "u"

    def test_select_with_alias(self):
        cols = extract_select_columns(
            "SELECT phone AS mobile FROM users", "mysql"
        )
        assert len(cols) == 1
        assert cols[0]["field"] == "phone"
        assert cols[0]["alias"] == "mobile"

    def test_pgsql_dialect(self):
        """验证 PostgreSQL 方言解析正常（1.x 中非 MySQL 脱敏失效问题）。"""
        cols = extract_select_columns(
            'SELECT id, email FROM "users" WHERE id = 1', "pgsql"
        )
        assert any(c["field"] == "email" for c in cols)

    def test_clickhouse_dialect(self):
        cols = extract_select_columns(
            "SELECT user_id, phone FROM events", "clickhouse"
        )
        assert len(cols) == 2

    def test_invalid_sql_returns_empty(self):
        cols = extract_select_columns("NOT VALID SQL !!!!", "mysql")
        assert cols == []


class TestExtractTableRefs:
    """测试表引用提取（用于查询权限校验，替代 goInception.query_print）。"""

    def test_simple_from(self):
        tables = extract_table_refs("SELECT * FROM users", "mydb", "mysql")
        assert len(tables) == 1
        assert tables[0]["name"] == "users"
        assert tables[0]["schema"] == "mydb"  # 默认填 db_name

    def test_explicit_schema(self):
        tables = extract_table_refs(
            "SELECT * FROM mydb.users", "defaultdb", "mysql"
        )
        assert tables[0]["schema"] == "mydb"
        assert tables[0]["name"] == "users"

    def test_pgsql_unqualified_table_does_not_treat_database_as_schema(self):
        tables = extract_table_refs(
            'SELECT * FROM "tk_order"', "tms_testdb", "pgsql"
        )
        assert tables[0]["schema"] == ""
        assert tables[0]["name"] == "tk_order"

    def test_join(self):
        tables = extract_table_refs(
            "SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id",
            "mydb", "mysql",
        )
        table_names = {t["name"] for t in tables}
        assert "users" in table_names
        assert "orders" in table_names

    def test_subquery(self):
        tables = extract_table_refs(
            "SELECT * FROM (SELECT id FROM users) AS sub",
            "mydb", "mysql",
        )
        assert any(t["name"] == "users" for t in tables)


class TestDataMaskingService:
    """测试数据脱敏规则应用。"""

    def test_phone_masking(self):
        rules = [{"column_name": "phone", "rule_type": "phone"}]
        svc = DataMaskingService(rules=rules)
        rs = ResultSet(
            column_list=["id", "phone"],
            rows=[(1, "13812345678"), (2, "18698765432")],
        )
        masked = svc.mask_result(rs, "SELECT id, phone FROM users", "mysql")
        # 手机号应被脱敏：保留前3后2
        phones = [row[1] for row in masked.rows]
        assert all("****" in p for p in phones)
        assert phones[0].startswith("138")
        assert phones[0].endswith("78")

    def test_email_masking(self):
        rules = [{"column_name": "email", "rule_type": "email"}]
        svc = DataMaskingService(rules=rules)
        rs = ResultSet(
            column_list=["email"],
            rows=[("test@example.com",), ("hello@gmail.com",)],
        )
        masked = svc.mask_result(rs, "SELECT email FROM users", "mysql")
        emails = [row[0] for row in masked.rows]
        assert all("***" in e for e in emails)
        # 保留前两位
        assert emails[0].startswith("te")
        assert "@example.com" in emails[0]

    def test_no_match_rule_returns_original(self):
        """未匹配到规则时，原始数据不变。"""
        rules = [{"column_name": "secret_col", "rule_type": "phone"}]
        svc = DataMaskingService(rules=rules)
        rs = ResultSet(
            column_list=["id", "name"],
            rows=[(1, "张三"), (2, "李四")],
        )
        masked = svc.mask_result(rs, "SELECT id, name FROM users", "mysql")
        # name 不在规则中，不应被脱敏
        assert masked.rows[0][1] == "张三"

    def test_empty_rules_returns_original(self):
        svc = DataMaskingService(rules=[])
        rs = ResultSet(
            column_list=["phone"],
            rows=[("13812345678",)],
        )
        masked = svc.mask_result(rs, "SELECT phone FROM users", "mysql")
        assert masked.rows[0][0] == "13812345678"

    def test_id_card_masking(self):
        rules = [{"column_name": "id_card", "rule_type": "id_card"}]
        svc = DataMaskingService(rules=rules)
        rs = ResultSet(
            column_list=["id_card"],
            rows=[("110101199001011234",)],
        )
        masked = svc.mask_result(rs, "SELECT id_card FROM users", "mysql")
        result = masked.rows[0][0]
        assert result.startswith("110")
        assert "***" in result

    def test_pgsql_masking_works(self):
        """验证 PgSQL 脱敏有效（1.x 中 goInception 只支持 MySQL 导致 PgSQL 脱敏失效）。"""
        rules = [{"column_name": "phone", "rule_type": "phone"}]
        svc = DataMaskingService(rules=rules)
        rs = ResultSet(
            column_list=["phone"],
            rows=[("13812345678",)],
        )
        # 使用 pgsql 方言
        masked = svc.mask_result(
            rs, 'SELECT phone FROM "users"', "pgsql"
        )
        assert "****" in masked.rows[0][0]

    def test_wildcard_column_masking(self):
        """列名支持 * 通配，和规则管理页面提示保持一致。"""
        rules = [{"column_name": "*phone*", "rule_type": "phone"}]
        svc = DataMaskingService(rules=rules)
        rs = ResultSet(
            column_list=["receiver_phone"],
            rows=[("13812345678",)],
        )
        masked = svc.mask_result(rs, "SELECT receiver_phone FROM orders", "mysql")
        assert masked.rows[0][0] == "138****78"

    def test_address_and_card_masking(self):
        rules = [
            {"column_name": "address", "rule_type": "address"},
            {"column_name": "bank_card", "rule_type": "card"},
        ]
        svc = DataMaskingService(rules=rules)
        rs = ResultSet(
            column_list=["address", "bank_card"],
            rows=[("上海市浦东新区世纪大道100号", "6222021202001234567")],
        )
        masked = svc.mask_result(rs, "SELECT address, bank_card FROM users", "mysql")
        assert masked.rows[0][0] == "上海市浦东新***"
        assert masked.rows[0][1] == "622202 **** **** 4567"
