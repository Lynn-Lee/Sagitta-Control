"""
InstanceService 元数据标准化测试。
"""

from app.services.instance import InstanceService


class TestNormalizeColumnRow:
    def test_mysql_dict_cursor_uppercase_keys(self):
        row = {
            "COLUMN_NAME": "id",
            "COLUMN_TYPE": "bigint(20)",
            "IS_NULLABLE": "NO",
            "COLUMN_DEFAULT": None,
            "COLUMN_COMMENT": "主键",
            "COLUMN_KEY": "PRI",
        }

        result = InstanceService._normalize_column_row(row, cols=[])

        assert result == {
            "column_name": "id",
            "column_type": "bigint(20)",
            "is_nullable": "NO",
            "column_default": None,
            "column_comment": "主键",
            "column_key": "PRI",
        }

    def test_pg_tuple_with_alias_fields(self):
        cols = ["column_name", "data_type", "is_nullable", "column_default"]
        row = ("created_at", "timestamp without time zone", "YES", "now()")

        result = InstanceService._normalize_column_row(row, cols=cols)

        assert result == {
            "column_name": "created_at",
            "column_type": "timestamp without time zone",
            "is_nullable": "YES",
            "column_default": "now()",
            "column_comment": "",
            "column_key": "",
        }

    def test_oracle_nullable_and_comment_aliases(self):
        row = {
            "column_name": "USER_ID",
            "data_type": "NUMBER",
            "nullable": "N",
            "data_default": "0",
            "comment": "用户ID",
        }

        result = InstanceService._normalize_column_row(row, cols=[])

        assert result == {
            "column_name": "USER_ID",
            "column_type": "NUMBER",
            "is_nullable": "N",
            "column_default": "0",
            "column_comment": "用户ID",
            "column_key": "",
        }


class TestNormalizeConstraintRow:
    def test_mysql_constraint_row(self):
        row = {
            "CONSTRAINT_NAME": "PRIMARY",
            "CONSTRAINT_TYPE": "PRIMARY KEY",
            "COLUMN_NAMES": "id",
            "REFERENCED_TABLE_NAME": None,
            "REFERENCED_COLUMN_NAMES": None,
        }

        result = InstanceService._normalize_constraint_row(row, cols=[])

        assert result == {
            "constraint_name": "PRIMARY",
            "constraint_type": "PRIMARY KEY",
            "column_names": "id",
            "referenced_table_name": "",
            "referenced_column_names": "",
        }

    def test_tuple_constraint_row(self):
        cols = [
            "constraint_name",
            "constraint_type",
            "column_names",
            "referenced_table_name",
            "referenced_column_names",
        ]
        row = ("uk_user_email", "UNIQUE", "email", None, None)

        result = InstanceService._normalize_constraint_row(row, cols=cols)

        assert result == {
            "constraint_name": "uk_user_email",
            "constraint_type": "UNIQUE",
            "column_names": "email",
            "referenced_table_name": "",
            "referenced_column_names": "",
        }


class TestNormalizeIndexRow:
    def test_mysql_index_row(self):
        row = {
            "INDEX_NAME": "idx_user_email",
            "INDEX_TYPE": "INDEX",
            "COLUMN_NAMES": "email, tenant_id",
            "IS_COMPOSITE": "YES",
            "INDEX_COMMENT": "用户邮箱联合索引",
        }

        result = InstanceService._normalize_index_row(row, cols=[])

        assert result == {
            "index_name": "idx_user_email",
            "index_type": "INDEX",
            "column_names": "email, tenant_id",
            "is_composite": "YES",
            "index_comment": "用户邮箱联合索引",
        }

    def test_tuple_index_row(self):
        cols = ["index_name", "index_type", "column_names", "is_composite", "index_comment"]
        row = ("users_pkey", "PRIMARY KEY INDEX", "id", "NO", "")

        result = InstanceService._normalize_index_row(row, cols=cols)

        assert result == {
            "index_name": "users_pkey",
            "index_type": "PRIMARY KEY INDEX",
            "column_names": "id",
            "is_composite": "NO",
            "index_comment": "",
        }
