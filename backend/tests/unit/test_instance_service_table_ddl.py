"""
InstanceService 表 DDL 生成测试。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.instance import InstanceService


class TestBuildGenericTableDDL:
    def test_builds_pg_style_create_table_with_constraints(self):
        instance = SimpleNamespace(db_type="pgsql")
        columns = [
            {
                "column_name": "id",
                "column_type": "bigint",
                "is_nullable": "NO",
                "column_default": None,
            },
            {
                "column_name": "email",
                "column_type": "character varying(128)",
                "is_nullable": "YES",
                "column_default": None,
            },
        ]
        constraints = [
            {
                "constraint_name": "users_pkey",
                "constraint_type": "PRIMARY KEY",
                "column_names": "id",
                "referenced_table_name": "",
                "referenced_column_names": "",
                "check_clause": "",
            },
            {
                "constraint_name": "users_email_key",
                "constraint_type": "UNIQUE",
                "column_names": "email",
                "referenced_table_name": "",
                "referenced_column_names": "",
                "check_clause": "",
            },
        ]

        ddl = InstanceService._build_generic_table_ddl(instance, "users", columns, constraints)

        assert 'CREATE TABLE "users" (' in ddl
        assert '  "id" bigint NOT NULL' in ddl
        assert '  PRIMARY KEY ("id")' in ddl
        assert '  CONSTRAINT "users_email_key" UNIQUE ("email")' in ddl

    def test_oracle_generated_ddl_normalizes_default_and_skips_system_not_null_checks(self):
        instance = SimpleNamespace(db_type="oracle")
        columns = [
            {
                "column_name": "CREATED_AT",
                "column_type": "TIMESTAMP(6)",
                "is_nullable": "N",
                "column_default": "CURRENT_TIMESTAMP\n",
                "column_comment": "创建时间",
            },
        ]
        constraints = [
            {
                "constraint_name": "SYS_C008612",
                "constraint_type": "CHECK",
                "column_names": "CREATED_AT",
                "referenced_table_name": "",
                "referenced_column_names": "",
                "check_clause": 'CHECK ("CREATED_AT" IS NOT NULL)',
            },
        ]

        ddl = InstanceService._build_generic_table_ddl(instance, "USERS_DEMO", columns, constraints)

        assert '"CREATED_AT" TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP' in ddl
        assert 'SYS_C008612' not in ddl
        assert 'CURRENT_TIMESTAMP\n,' not in ddl
        assert 'COMMENT ON COLUMN "USERS_DEMO"."CREATED_AT" IS \'创建时间\';' in ddl

    def test_pg_generated_ddl_appends_column_comments(self):
        instance = SimpleNamespace(db_type="pgsql")
        columns = [
            {
                "column_name": "create_code",
                "column_type": "character varying(32)",
                "is_nullable": "YES",
                "column_default": None,
                "column_comment": "创建人编码",
            },
        ]

        ddl = InstanceService._build_generic_table_ddl(instance, "t_basic_cost_detail", columns, [])

        assert 'CREATE TABLE "t_basic_cost_detail" (' in ddl
        assert 'COMMENT ON COLUMN "t_basic_cost_detail"."create_code" IS \'创建人编码\';' in ddl

    def test_pg_generated_ddl_appends_non_constraint_indexes(self):
        instance = SimpleNamespace(db_type="pgsql")
        columns = [
            {
                "column_name": "id",
                "column_type": "integer",
                "is_nullable": "NO",
                "column_default": None,
            },
            {
                "column_name": "create_code",
                "column_type": "character varying",
                "is_nullable": "YES",
                "column_default": None,
            },
            {
                "column_name": "create_name",
                "column_type": "character varying",
                "is_nullable": "YES",
                "column_default": None,
            },
        ]
        constraints = [
            {
                "constraint_name": "t_basic_cost_detail_pkey",
                "constraint_type": "PRIMARY KEY",
                "column_names": "id",
            },
            {
                "constraint_name": "t_basic_cost_detail_create_code_key",
                "constraint_type": "UNIQUE",
                "column_names": "create_code",
            },
        ]
        indexes = [
            {
                "index_name": "t_basic_cost_detail_pkey",
                "index_type": "PRIMARY KEY INDEX",
                "column_names": "id",
                "index_definition": 'CREATE UNIQUE INDEX t_basic_cost_detail_pkey ON public.t_basic_cost_detail USING btree (id)',
            },
            {
                "index_name": "t_basic_cost_detail_create_code_key",
                "index_type": "UNIQUE INDEX",
                "column_names": "create_code",
                "index_definition": 'CREATE UNIQUE INDEX t_basic_cost_detail_create_code_key ON public.t_basic_cost_detail USING btree (create_code)',
            },
            {
                "index_name": "idx_t_basic_cost_detail_01",
                "index_type": "INDEX",
                "column_names": "create_code, create_name",
                "index_definition": 'CREATE INDEX idx_t_basic_cost_detail_01 ON public.t_basic_cost_detail USING btree (create_code, create_name)',
            },
        ]

        ddl = InstanceService._build_generic_table_ddl(
            instance,
            "t_basic_cost_detail",
            columns,
            constraints,
            indexes,
        )

        assert 'PRIMARY KEY ("id")' in ddl
        assert 'CONSTRAINT "t_basic_cost_detail_create_code_key" UNIQUE ("create_code")' in ddl
        assert "CREATE INDEX idx_t_basic_cost_detail_01 ON public.t_basic_cost_detail USING btree (create_code, create_name);" in ddl
        assert "CREATE UNIQUE INDEX t_basic_cost_detail_pkey" not in ddl
        assert "CREATE UNIQUE INDEX t_basic_cost_detail_create_code_key" not in ddl


class TestGetTableDDL:
    @pytest.mark.asyncio
    async def test_prefers_engine_show_create_table_when_available(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        instance = SimpleNamespace(db_type="mysql")
        engine = SimpleNamespace(
            describe_table=AsyncMock(
                return_value=SimpleNamespace(
                    is_success=True,
                    column_list=["Table", "Create Table"],
                    rows=[{"Table": "users", "Create Table": "CREATE TABLE `users` (`id` bigint)"}],
                )
            )
        )
        monkeypatch.setattr(InstanceService, "_load_instance", AsyncMock(return_value=instance))
        monkeypatch.setattr("app.services.instance.get_engine", lambda _instance: engine)

        result = await InstanceService.get_table_ddl(SimpleNamespace(), 1, "demo", "users")

        assert result == {
            "table_name": "users",
            "ddl": "CREATE TABLE `users` (`id` bigint)",
            "copyable_ddl": "CREATE TABLE `users` (`id` bigint)",
            "raw_ddl": "CREATE TABLE `users` (`id` bigint)",
            "source": "engine",
        }

    @pytest.mark.asyncio
    async def test_oracle_returns_copyable_and_raw_ddl(self, monkeypatch: pytest.MonkeyPatch):
        instance = SimpleNamespace(db_type="oracle")
        raw_ddl = '''CREATE TABLE "DEMO_SCHEMA"."USERS_DEMO"
(
  "ID" NUMBER GENERATED BY DEFAULT AS IDENTITY MINVALUE 1 MAXVALUE 999999 CACHE 20 NOORDER NOCYCLE NOT NULL ENABLE,
  "USERNAME" VARCHAR2(50) NOT NULL ENABLE,
  PRIMARY KEY ("ID")
  USING INDEX PCTFREE 10 INITRANS 2 MAXTRANS 255
  STORAGE(INITIAL 65536 NEXT 1048576 MINEXTENTS 1 MAXEXTENTS 2147483645
  PCTINCREASE 0 FREELISTS 1 FREELIST GROUPS 1
  BUFFER_POOL DEFAULT FLASH_CACHE DEFAULT CELL_FLASH_CACHE DEFAULT)
  TABLESPACE "USERS" ENABLE
)
SEGMENT CREATION IMMEDIATE
PCTFREE 10 PCTUSED 40 INITRANS 1 MAXTRANS 255
NOCOMPRESS LOGGING
STORAGE(INITIAL 65536 NEXT 1048576 MINEXTENTS 1 MAXEXTENTS 2147483645
PCTINCREASE 0 FREELISTS 1 FREELIST GROUPS 1
BUFFER_POOL DEFAULT FLASH_CACHE DEFAULT CELL_FLASH_CACHE DEFAULT)
TABLESPACE "USERS"
);'''
        engine = SimpleNamespace(
            describe_table=AsyncMock(
                return_value=SimpleNamespace(
                    is_success=True,
                    column_list=["CREATE TABLE"],
                    rows=[(raw_ddl,)],
                )
            )
        )
        monkeypatch.setattr(InstanceService, "_load_instance", AsyncMock(return_value=instance))
        monkeypatch.setattr(
            InstanceService,
            "get_columns",
            AsyncMock(
                return_value=[
                    {
                        "column_name": "CREATED_AT",
                        "column_type": "TIMESTAMP(6)",
                        "is_nullable": "Y",
                        "column_default": "CURRENT_TIMESTAMP",
                        "column_comment": "创建时间",
                    }
                ]
            ),
        )
        monkeypatch.setattr("app.services.instance.get_engine", lambda _instance: engine)

        result = await InstanceService.get_table_ddl(SimpleNamespace(), 1, "DEMO_SCHEMA", "USERS_DEMO")

        assert str(result["raw_ddl"]).startswith(raw_ddl)
        assert "STORAGE" in str(result["raw_ddl"])
        assert "TABLESPACE" in str(result["raw_ddl"])
        assert "SEGMENT CREATION" in str(result["raw_ddl"])
        assert 'COMMENT ON COLUMN "DEMO_SCHEMA"."USERS_DEMO"."CREATED_AT" IS \'创建时间\';' in str(result["raw_ddl"])
        assert result["ddl"] == result["copyable_ddl"]
        assert 'CREATE TABLE "USERS_DEMO"' in str(result["copyable_ddl"])
        assert 'CREATE TABLE "DEMO_SCHEMA"."USERS_DEMO"' not in str(result["copyable_ddl"])
        assert "USING INDEX" not in str(result["copyable_ddl"])
        assert "STORAGE" not in str(result["copyable_ddl"])
        assert "TABLESPACE" not in str(result["copyable_ddl"])
        assert "SEGMENT CREATION" not in str(result["copyable_ddl"])
        assert "PCTFREE" not in str(result["copyable_ddl"])
        assert "PCTUSED" not in str(result["copyable_ddl"])
        assert "INITRANS" not in str(result["copyable_ddl"])
        assert "MAXTRANS" not in str(result["copyable_ddl"])
        assert "BUFFER_POOL" not in str(result["copyable_ddl"])
        assert "FLASH_CACHE" not in str(result["copyable_ddl"])
        assert "CELL_FLASH_CACHE" not in str(result["copyable_ddl"])
        assert " ENABLE" not in str(result["copyable_ddl"])
        assert 'COMMENT ON COLUMN "DEMO_SCHEMA"."USERS_DEMO"."CREATED_AT" IS \'创建时间\';' in str(result["copyable_ddl"])
