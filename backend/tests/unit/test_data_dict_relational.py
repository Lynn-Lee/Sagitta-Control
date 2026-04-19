"""
关系型数据库数据字典服务测试。

覆盖：
- MySQL / TiDB / PostgreSQL / Oracle / MSSQL
- 列 / 约束 / 索引三类元数据在服务层的统一归一化
"""

from types import SimpleNamespace

import pytest

from app.engines.models import ResultSet
from app.services.instance import InstanceService


class FakeEngine:
    def __init__(
        self,
        columns: ResultSet | None = None,
        constraints: ResultSet | None = None,
        indexes: ResultSet | None = None,
    ) -> None:
        self._columns = columns or ResultSet()
        self._constraints = constraints or ResultSet()
        self._indexes = indexes or ResultSet()

    async def get_all_columns_by_tb(self, db_name: str, tb_name: str, **kwargs):
        return self._columns

    async def get_table_constraints(self, db_name: str, tb_name: str, **kwargs):
        return self._constraints

    async def get_table_indexes(self, db_name: str, tb_name: str, **kwargs):
        return self._indexes


async def _stub_load_instance(_db, _instance_id):
    return SimpleNamespace(id=1, db_type="stub")


def _patch_engine(monkeypatch: pytest.MonkeyPatch, engine: FakeEngine) -> None:
    monkeypatch.setattr(InstanceService, "_load_instance", staticmethod(_stub_load_instance))
    monkeypatch.setattr("app.services.instance.get_engine", lambda inst: engine)


class TestRelationalDataDictColumns:
    @pytest.mark.asyncio
    async def test_mysql_columns_are_normalized(self, monkeypatch: pytest.MonkeyPatch):
        engine = FakeEngine(
            columns=ResultSet(
                rows=[
                    {
                        "COLUMN_NAME": "id",
                        "COLUMN_TYPE": "bigint(20)",
                        "IS_NULLABLE": "NO",
                        "COLUMN_DEFAULT": None,
                        "COLUMN_COMMENT": "主键",
                        "COLUMN_KEY": "PRI",
                    }
                ]
            )
        )
        _patch_engine(monkeypatch, engine)

        result = await InstanceService.get_columns(None, 1, "demo", "users")

        assert result == [
            {
                "column_name": "id",
                "column_type": "bigint(20)",
                "is_nullable": "NO",
                "column_default": None,
                "column_comment": "主键",
                "column_key": "PRI",
            }
        ]

    @pytest.mark.asyncio
    async def test_tidb_columns_follow_mysql_shape(self, monkeypatch: pytest.MonkeyPatch):
        engine = FakeEngine(
            columns=ResultSet(
                rows=[
                    {
                        "COLUMN_NAME": "created_at",
                        "COLUMN_TYPE": "timestamp",
                        "IS_NULLABLE": "YES",
                        "COLUMN_DEFAULT": "CURRENT_TIMESTAMP",
                        "COLUMN_COMMENT": "",
                        "COLUMN_KEY": "",
                    }
                ]
            )
        )
        _patch_engine(monkeypatch, engine)

        result = await InstanceService.get_columns(None, 1, "demo", "orders")

        assert result[0]["column_name"] == "created_at"
        assert result[0]["column_type"] == "timestamp"
        assert result[0]["column_default"] == "CURRENT_TIMESTAMP"

    @pytest.mark.asyncio
    async def test_pgsql_columns_are_normalized(self, monkeypatch: pytest.MonkeyPatch):
        engine = FakeEngine(
            columns=ResultSet(
                column_list=["column_name", "data_type", "is_nullable", "column_default"],
                rows=[("email", "character varying", "NO", None)],
            )
        )
        _patch_engine(monkeypatch, engine)

        result = await InstanceService.get_columns(None, 1, "demo", "users")

        assert result == [
            {
                "column_name": "email",
                "column_type": "character varying",
                "is_nullable": "NO",
                "column_default": None,
                "column_comment": "",
                "column_key": "",
            }
        ]

    @pytest.mark.asyncio
    async def test_oracle_columns_are_normalized(self, monkeypatch: pytest.MonkeyPatch):
        engine = FakeEngine(
            columns=ResultSet(
                rows=[
                    {
                        "column_name": "USER_ID",
                        "data_type": "NUMBER",
                        "nullable": "N",
                        "data_default": "0",
                        "comment": "用户ID",
                    }
                ]
            )
        )
        _patch_engine(monkeypatch, engine)

        result = await InstanceService.get_columns(None, 1, "HR", "USERS")

        assert result == [
            {
                "column_name": "USER_ID",
                "column_type": "NUMBER",
                "is_nullable": "N",
                "column_default": "0",
                "column_comment": "用户ID",
                "column_key": "",
            }
        ]

    @pytest.mark.asyncio
    async def test_mssql_columns_are_normalized(self, monkeypatch: pytest.MonkeyPatch):
        engine = FakeEngine(
            columns=ResultSet(
                rows=[
                    {
                        "column_name": "message_id",
                        "column_type": "nvarchar(64)",
                        "is_nullable": "NO",
                        "column_default": "('')",
                        "column_comment": "消息ID",
                    }
                ]
            )
        )
        _patch_engine(monkeypatch, engine)

        result = await InstanceService.get_columns(None, 1, "demo", "messages")

        assert result == [
            {
                "column_name": "message_id",
                "column_type": "nvarchar(64)",
                "is_nullable": "NO",
                "column_default": "('')",
                "column_comment": "消息ID",
                "column_key": "",
            }
        ]


class TestRelationalDataDictConstraints:
    @pytest.mark.asyncio
    async def test_mysql_constraints_are_normalized(self, monkeypatch: pytest.MonkeyPatch):
        engine = FakeEngine(
            constraints=ResultSet(
                rows=[
                    {
                        "CONSTRAINT_NAME": "PRIMARY",
                        "CONSTRAINT_TYPE": "PRIMARY KEY",
                        "COLUMN_NAMES": "id",
                        "REFERENCED_TABLE_NAME": None,
                        "REFERENCED_COLUMN_NAMES": None,
                    }
                ]
            )
        )
        _patch_engine(monkeypatch, engine)

        result = await InstanceService.get_constraints(None, 1, "demo", "users")

        assert result == [
            {
                "constraint_name": "PRIMARY",
                "constraint_type": "PRIMARY KEY",
                "column_names": "id",
                "referenced_table_name": "",
                "referenced_column_names": "",
            }
        ]

    @pytest.mark.asyncio
    async def test_pgsql_foreign_key_constraints_are_normalized(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        engine = FakeEngine(
            constraints=ResultSet(
                column_list=[
                    "constraint_name",
                    "constraint_type",
                    "column_names",
                    "referenced_table_name",
                    "referenced_column_names",
                ],
                rows=[("fk_orders_user", "FOREIGN KEY", "user_id", "users", "id")],
            )
        )
        _patch_engine(monkeypatch, engine)

        result = await InstanceService.get_constraints(None, 1, "demo", "orders")

        assert result == [
            {
                "constraint_name": "fk_orders_user",
                "constraint_type": "FOREIGN KEY",
                "column_names": "user_id",
                "referenced_table_name": "users",
                "referenced_column_names": "id",
            }
        ]

    @pytest.mark.asyncio
    async def test_oracle_constraint_type_mapping_is_preserved(self, monkeypatch: pytest.MonkeyPatch):
        engine = FakeEngine(
            constraints=ResultSet(
                rows=[
                    {
                        "constraint_name": "UK_USER_EMAIL",
                        "constraint_type": "UNIQUE",
                        "column_names": "EMAIL",
                        "referenced_table_name": "",
                        "referenced_column_names": "",
                    }
                ]
            )
        )
        _patch_engine(monkeypatch, engine)

        result = await InstanceService.get_constraints(None, 1, "HR", "USERS")

        assert result[0]["constraint_type"] == "UNIQUE"
        assert result[0]["column_names"] == "EMAIL"

    @pytest.mark.asyncio
    async def test_mssql_constraints_are_normalized(self, monkeypatch: pytest.MonkeyPatch):
        engine = FakeEngine(
            constraints=ResultSet(
                rows=[
                    {
                        "constraint_name": "PK_messages",
                        "constraint_type": "PRIMARY KEY",
                        "column_names": "id",
                        "referenced_table_name": "",
                        "referenced_column_names": "",
                    }
                ]
            )
        )
        _patch_engine(monkeypatch, engine)

        result = await InstanceService.get_constraints(None, 1, "demo", "messages")

        assert result[0]["constraint_name"] == "PK_messages"
        assert result[0]["constraint_type"] == "PRIMARY KEY"


class TestRelationalDataDictIndexes:
    @pytest.mark.asyncio
    async def test_mysql_indexes_are_normalized(self, monkeypatch: pytest.MonkeyPatch):
        engine = FakeEngine(
            indexes=ResultSet(
                rows=[
                    {
                        "INDEX_NAME": "idx_user_email",
                        "INDEX_TYPE": "INDEX",
                        "COLUMN_NAMES": "email, tenant_id",
                        "IS_COMPOSITE": "YES",
                        "INDEX_COMMENT": "联合检索",
                    }
                ]
            )
        )
        _patch_engine(monkeypatch, engine)

        result = await InstanceService.get_indexes(None, 1, "demo", "users")

        assert result == [
            {
                "index_name": "idx_user_email",
                "index_type": "INDEX",
                "column_names": "email, tenant_id",
                "is_composite": "YES",
                "index_comment": "联合检索",
            }
        ]

    @pytest.mark.asyncio
    async def test_tidb_indexes_follow_mysql_shape(self, monkeypatch: pytest.MonkeyPatch):
        engine = FakeEngine(
            indexes=ResultSet(
                rows=[
                    {
                        "INDEX_NAME": "uk_order_no",
                        "INDEX_TYPE": "UNIQUE INDEX",
                        "COLUMN_NAMES": "order_no",
                        "IS_COMPOSITE": "NO",
                        "INDEX_COMMENT": "",
                    }
                ]
            )
        )
        _patch_engine(monkeypatch, engine)

        result = await InstanceService.get_indexes(None, 1, "demo", "orders")

        assert result[0]["index_type"] == "UNIQUE INDEX"
        assert result[0]["column_names"] == "order_no"

    @pytest.mark.asyncio
    async def test_pgsql_indexes_are_normalized(self, monkeypatch: pytest.MonkeyPatch):
        engine = FakeEngine(
            indexes=ResultSet(
                column_list=[
                    "index_name",
                    "index_type",
                    "column_names",
                    "is_composite",
                    "index_comment",
                ],
                rows=[("users_pkey", "PRIMARY KEY INDEX", "id", "NO", "")],
            )
        )
        _patch_engine(monkeypatch, engine)

        result = await InstanceService.get_indexes(None, 1, "demo", "users")

        assert result == [
            {
                "index_name": "users_pkey",
                "index_type": "PRIMARY KEY INDEX",
                "column_names": "id",
                "is_composite": "NO",
                "index_comment": "",
            }
        ]

    @pytest.mark.asyncio
    async def test_oracle_indexes_are_normalized(self, monkeypatch: pytest.MonkeyPatch):
        engine = FakeEngine(
            indexes=ResultSet(
                rows=[
                    {
                        "index_name": "IDX_USERS_EMAIL",
                        "index_type": "UNIQUE INDEX",
                        "column_names": "EMAIL",
                        "is_composite": "NO",
                        "index_comment": "",
                    }
                ]
            )
        )
        _patch_engine(monkeypatch, engine)

        result = await InstanceService.get_indexes(None, 1, "HR", "USERS")

        assert result[0]["index_name"] == "IDX_USERS_EMAIL"
        assert result[0]["index_type"] == "UNIQUE INDEX"

    @pytest.mark.asyncio
    async def test_mssql_indexes_are_normalized(self, monkeypatch: pytest.MonkeyPatch):
        engine = FakeEngine(
            indexes=ResultSet(
                rows=[
                    {
                        "index_name": "IX_messages_status_created",
                        "index_type": "INDEX",
                        "column_names": "status, created_at",
                        "is_composite": "YES",
                        "index_comment": "",
                    }
                ]
            )
        )
        _patch_engine(monkeypatch, engine)

        result = await InstanceService.get_indexes(None, 1, "demo", "messages")

        assert result == [
            {
                "index_name": "IX_messages_status_created",
                "index_type": "INDEX",
                "column_names": "status, created_at",
                "is_composite": "YES",
                "index_comment": "",
            }
        ]
