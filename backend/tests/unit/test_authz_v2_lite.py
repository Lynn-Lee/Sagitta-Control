"""
v2-lite 权限体系单元测试。
"""

from datetime import date
from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppException
from app.engines.models import ResultSet
from app.engines.oracle import OracleEngine
from app.schemas.approval_flow import ApprovalFlowNodeCreate
from app.schemas.query import AuditPrivRequest, PrivApplyRequest
from app.services.governance_scope import GovernanceScopeService
from app.services.monitor import MonitorService
from app.services.query_priv import QueryPrivService
from app.services.role import BUILTIN_ROLES
from app.services.user import UserService


def _role_permissions(name: str) -> set[str]:
    for role in BUILTIN_ROLES:
        if role["name"] == name:
            return set(role["permissions"])
    raise AssertionError(f"role {name} not found")


class TestBuiltinRolePermissions:
    def test_developer_is_menu_query_only_for_core_entry(self):
        developer = _role_permissions("developer")
        assert "menu_query" in developer
        assert "menu_schema" in developer
        assert "menu_monitor" not in developer
        assert "process_view" not in developer
        assert "archive_apply" not in developer

    def test_dba_group_is_resource_scoped_monitor_admin(self):
        dba_group = _role_permissions("dba_group")
        assert "menu_monitor" in dba_group
        assert "monitor_config_manage" in dba_group
        assert "monitor_all_instances" not in dba_group


class TestApprovalFlowNodeSchema:
    def test_users_type_requires_explicit_approvers(self):
        with pytest.raises(ValidationError):
            ApprovalFlowNodeCreate(order=1, node_name="指定审批人", approver_type="users")

    def test_manager_type_does_not_require_ids(self):
        node = ApprovalFlowNodeCreate(order=1, node_name="直属上级", approver_type="manager")
        assert node.approver_ids == []

    def test_any_reviewer_type_does_not_require_ids(self):
        node = ApprovalFlowNodeCreate(order=1, node_name="任意审批员", approver_type="any_reviewer")
        assert node.approver_ids == []


class TestQueryPrivilegeSchema:
    def test_instance_scope_can_omit_db_and_table_name(self):
        req = PrivApplyRequest(
            title="申请实例级权限",
            instance_id=1,
            db_name="",
            table_name="",
            valid_date="2099-01-01",
            limit_num=100,
            priv_type=0,
            apply_reason="需要排查问题",
            audit_auth_groups="1",
            scope_type="instance",
        )
        assert req.scope_type == "instance"
        assert req.db_name == ""
        assert req.table_name == ""

    def test_table_scope_requires_table_name(self):
        with pytest.raises(ValidationError):
            PrivApplyRequest(
                title="申请表级权限",
                instance_id=1,
                db_name="analytics",
                table_name="",
                valid_date="2099-01-01",
                limit_num=100,
                priv_type=2,
                apply_reason="需要排查问题",
                audit_auth_groups="1",
                scope_type="table",
            )

    def test_database_scope_can_omit_table_name(self):
        req = PrivApplyRequest(
            title="申请库级权限",
            instance_id=1,
            db_name="analytics",
            table_name="",
            valid_date="2099-01-01",
            limit_num=100,
            priv_type=1,
            apply_reason="需要排查问题",
            audit_auth_groups="1",
            scope_type="database",
        )
        assert req.scope_type == "database"

    def test_audit_valid_date_must_not_be_past(self):
        with pytest.raises(ValidationError):
            AuditPrivRequest(action="pass", valid_date="2000-01-01")


class TestResourceScopedAccess:
    def test_query_access_respects_resource_group_intersection(self):
        instance = SimpleNamespace(resource_groups=[SimpleNamespace(id=2), SimpleNamespace(id=3)])
        user = {"resource_groups": [1, 3], "permissions": [], "is_superuser": False}
        assert QueryPrivService.user_has_instance_access(user, instance) is True

    def test_monitor_access_respects_resource_group_intersection(self):
        instance = SimpleNamespace(resource_groups=[SimpleNamespace(id=5)])
        user = {"resource_groups": [2, 5], "permissions": [], "is_superuser": False}
        assert MonitorService._can_access_instance(user, instance) is True

    def test_monitor_access_denies_out_of_scope_instance(self):
        instance = SimpleNamespace(resource_groups=[SimpleNamespace(id=8)])
        user = {"resource_groups": [2, 5], "permissions": [], "is_superuser": False}
        assert MonitorService._can_access_instance(user, instance) is False


class TestGovernanceScope:
    @pytest.mark.asyncio
    async def test_global_query_scope_for_query_all_instances(self):
        scope = await GovernanceScopeService.resolve(
            AsyncMock(),
            {
                "id": 7,
                "role": "developer",
                "permissions": ["query_all_instances"],
                "is_superuser": False,
            },
            "query",
        )

        assert scope["mode"] == "global"
        assert scope["label"] == "全量数据"

    @pytest.mark.asyncio
    async def test_resource_group_dba_scope_resolves_instance_ids(self):
        result = MagicMock()
        result.scalars.return_value.all.return_value = [11, 12]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)

        scope = await GovernanceScopeService.resolve(
            db,
            {
                "id": 8,
                "role": "dba_group",
                "permissions": ["query_mgtpriv"],
                "resource_groups": [2],
                "is_superuser": False,
            },
            "query",
        )

        assert scope["mode"] == "instance_scope"
        assert scope["instance_ids"] == [11, 12]

    @pytest.mark.asyncio
    async def test_group_leader_scope_includes_active_members_and_self(self):
        group = SimpleNamespace(
            members=[
                SimpleNamespace(id=9, is_active=True),
                SimpleNamespace(id=10, is_active=False),
            ]
        )
        result = MagicMock()
        result.scalars.return_value.all.return_value = [group]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)

        scope = await GovernanceScopeService.resolve(
            db,
            {
                "id": 7,
                "role": "developer",
                "permissions": [],
                "is_superuser": False,
            },
            "workflow",
        )

        assert scope["mode"] == "group"
        assert scope["user_ids"] == [7, 9]


class TestQueryPrivilegeHelpers:
    def test_instance_scope_normalizes_to_instance_priv(self):
        assert QueryPrivService._normalize_scope_type("instance", "", "") == ("instance", 0)

    def test_table_scope_normalizes_to_table_priv(self):
        assert QueryPrivService._normalize_scope_type("table", "", "") == ("table", 2)

    def test_table_name_also_forces_table_scope(self):
        assert QueryPrivService._normalize_scope_type("database", "orders", "") == ("table", 2)

    def test_database_scope_normalizes_to_database_priv(self):
        assert QueryPrivService._normalize_scope_type("database", "", "analytics") == ("database", 1)

    def test_pg_table_candidates_include_plain_and_schema_qualified_name(self):
        assert QueryPrivService._pg_table_candidates("tms", "tk_order") == [
            "tk_order",
            "tms.tk_order",
        ]

    @pytest.mark.asyncio
    async def test_effective_query_limit_uses_stricter_table_privilege_limit(self):
        db = AsyncMock()
        table_result = MagicMock()
        table_result.scalars.return_value.first.return_value = SimpleNamespace(limit_num=1000)
        db.execute = AsyncMock(return_value=table_result)

        effective_limit = await QueryPrivService.get_effective_query_limit(
            db=db,
            user={"id": 7, "permissions": [], "is_superuser": False},
            instance=SimpleNamespace(id=9, db_type="mysql"),
            db_name="analytics",
            sql="SELECT * FROM orders",
            requested_limit=2000,
        )

        assert effective_limit == 1000

    @pytest.mark.asyncio
    async def test_effective_query_limit_prefers_latest_table_over_database_scope(self):
        db = AsyncMock()
        table_result = MagicMock()
        table_result.scalars.return_value.first.return_value = SimpleNamespace(limit_num=500)
        db.execute = AsyncMock(return_value=table_result)

        effective_limit = await QueryPrivService.get_effective_query_limit(
            db=db,
            user={"id": 7, "permissions": [], "is_superuser": False},
            instance=SimpleNamespace(id=9, db_type="mysql"),
            db_name="analytics",
            sql="SELECT * FROM orders",
            requested_limit=2000,
        )

        assert effective_limit == 500

    @pytest.mark.asyncio
    async def test_apply_privilege_requires_approval_flow(self):
        with pytest.raises(AppException) as exc_info:
            await QueryPrivService.apply_privilege(
                db=AsyncMock(),
                user_id=7,
                instance_id=1,
                group_id=None,
                flow_id=None,
                db_name="analytics",
                table_name="orders",
                valid_date=date(2099, 1, 1),
                limit_num=100,
                priv_type=2,
                apply_reason="排查问题",
                audit_auth_groups="",
                title="表权限申请",
                scope_type="table",
                user={"id": 7, "username": "dev1"},
            )

        assert exc_info.value.message == "请选择审批流"

    @pytest.mark.asyncio
    async def test_audit_apply_can_shorten_valid_date(self):
        apply = SimpleNamespace(
            id=99,
            status=0,
            flow_id=None,
            audit_auth_groups_info="",
            user_id=7,
            user_group_id=None,
            instance_id=1,
            resource_group_id=None,
            scope_type="database",
            db_name="analytics",
            table_name="",
            valid_date=date(2099, 1, 31),
            limit_num=100,
            priv_type=1,
        )
        result = MagicMock()
        result.scalar_one_or_none.return_value = apply
        db = SimpleNamespace(
            execute=AsyncMock(return_value=result),
            add=MagicMock(),
            commit=AsyncMock(),
            refresh=AsyncMock(),
        )

        await QueryPrivService.audit_apply(
            db=db,
            apply_id=99,
            auditor={"id": 1, "username": "admin", "is_superuser": True},
            action="pass",
            valid_date_override=date(2099, 1, 15),
        )

        assert apply.valid_date == date(2099, 1, 15)
        assert db.add.call_args.args[0].valid_date == date(2099, 1, 15)

    @pytest.mark.asyncio
    async def test_check_data_dict_access_accepts_instance_scope_privilege(self):
        instance = SimpleNamespace(id=1, db_type="mysql", resource_groups=[SimpleNamespace(id=2)])
        db = AsyncMock()

        async def fake_execute(_stmt):
            result = MagicMock()
            result.scalars.return_value.first.return_value = SimpleNamespace(id=1)
            return result

        db.execute = AsyncMock(side_effect=fake_execute)

        allowed, reason = await QueryPrivService.check_data_dict_access(
            db=db,
            user={"id": 7, "permissions": [], "resource_groups": [2], "is_superuser": False},
            instance=instance,
        )

        assert allowed is True
        assert reason == "instance_privilege"

    @pytest.mark.asyncio
    async def test_check_data_dict_access_accepts_table_scope_on_root_entry(self):
        instance = SimpleNamespace(id=1, db_type="mysql", resource_groups=[SimpleNamespace(id=2)])
        db = AsyncMock()

        async def fake_execute(_stmt):
            result = MagicMock()
            result.scalars.return_value.first.return_value = None
            return result

        db.execute = AsyncMock(side_effect=fake_execute)
        QueryPrivService._has_any_data_dict_priv = AsyncMock(return_value=True)  # type: ignore[method-assign]

        allowed, reason = await QueryPrivService.check_data_dict_access(
            db=db,
            user={"id": 7, "permissions": [], "resource_groups": [2], "is_superuser": False},
            instance=instance,
        )

        assert allowed is True
        assert reason == "scoped_privilege"

    @pytest.mark.asyncio
    async def test_check_data_dict_access_accepts_table_scope_on_database_entry(self):
        instance = SimpleNamespace(id=1, db_type="mysql", resource_groups=[SimpleNamespace(id=2)])
        db = AsyncMock()

        QueryPrivService._has_instance_priv = AsyncMock(return_value=False)  # type: ignore[method-assign]
        QueryPrivService._has_db_priv = AsyncMock(return_value=False)  # type: ignore[method-assign]
        QueryPrivService._has_any_table_priv_in_db = AsyncMock(return_value=True)  # type: ignore[method-assign]

        allowed, reason = await QueryPrivService.check_data_dict_access(
            db=db,
            user={"id": 7, "permissions": [], "resource_groups": [2], "is_superuser": False},
            instance=instance,
            db_name="ump_testdb",
        )

        assert allowed is True
        assert reason == "table_privilege_in_database"

    @pytest.mark.asyncio
    async def test_check_data_dict_access_denies_without_matching_scope(self):
        instance = SimpleNamespace(id=1, db_type="mysql", resource_groups=[SimpleNamespace(id=2)])
        empty_result = MagicMock()
        empty_result.scalars.return_value.first.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=empty_result)
        QueryPrivService._has_any_data_dict_priv = AsyncMock(return_value=False)  # type: ignore[method-assign]
        QueryPrivService._has_any_table_priv_in_db = AsyncMock(return_value=False)  # type: ignore[method-assign]

        allowed, reason = await QueryPrivService.check_data_dict_access(
            db=db,
            user={"id": 7, "permissions": [], "resource_groups": [2], "is_superuser": False},
            instance=instance,
            db_name="analytics",
            table_name="orders",
        )

        assert allowed is False
        assert "数据字典访问权限" in reason

    @pytest.mark.asyncio
    async def test_audit_apply_rejects_extending_valid_date(self):
        apply = SimpleNamespace(
            id=99,
            status=0,
            flow_id=None,
            audit_auth_groups_info="",
            valid_date=date(2099, 1, 31),
        )
        result = MagicMock()
        result.scalar_one_or_none.return_value = apply
        db = SimpleNamespace(
            execute=AsyncMock(return_value=result),
            add=MagicMock(),
            commit=AsyncMock(),
            refresh=AsyncMock(),
        )

        with pytest.raises(AppException) as exc_info:
            await QueryPrivService.audit_apply(
                db=db,
                apply_id=99,
                auditor={"id": 1, "username": "admin", "is_superuser": True},
                action="pass",
                valid_date_override=date(2099, 2, 1),
            )

        assert exc_info.value.message == "审批调整后的有效期不能超过申请有效期"

    @pytest.mark.asyncio
    async def test_revoke_privilege_allows_owner_without_manage_permission(self):
        priv = SimpleNamespace(id=9, user_id=7, instance_id=1, is_deleted=0)
        priv_result = MagicMock()
        priv_result.scalar_one_or_none.return_value = priv
        db = SimpleNamespace(
            execute=AsyncMock(return_value=priv_result),
            commit=AsyncMock(),
            refresh=AsyncMock(),
        )

        await QueryPrivService.revoke_privilege(
            db,
            priv_id=9,
            operator={"id": 7, "permissions": [], "is_superuser": False},
        )

        assert priv.is_deleted == 1
        assert priv.revoked_by_id == 7
        assert priv.revoked_at is not None
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_revoke_privilege_allows_resource_group_dba_in_scope(self):
        priv = SimpleNamespace(id=9, user_id=7, instance_id=1, is_deleted=0)
        instance = SimpleNamespace(resource_groups=[SimpleNamespace(id=2), SimpleNamespace(id=3)])
        priv_result = MagicMock()
        priv_result.scalar_one_or_none.return_value = priv
        instance_result = MagicMock()
        instance_result.scalar_one_or_none.return_value = instance
        db = SimpleNamespace(
            execute=AsyncMock(side_effect=[priv_result, instance_result]),
            commit=AsyncMock(),
            refresh=AsyncMock(),
        )

        await QueryPrivService.revoke_privilege(
            db,
            priv_id=9,
            operator={
                "id": 8,
                "permissions": ["query_mgtpriv"],
                "resource_groups": [3],
                "is_superuser": False,
            },
        )

        assert priv.is_deleted == 1
        assert priv.revoked_by_id == 8
        assert priv.revoked_at is not None
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_revoke_privilege_denies_resource_group_dba_out_of_scope(self):
        priv = SimpleNamespace(id=9, user_id=7, instance_id=1, is_deleted=0)
        instance = SimpleNamespace(resource_groups=[SimpleNamespace(id=2)])
        priv_result = MagicMock()
        priv_result.scalar_one_or_none.return_value = priv
        instance_result = MagicMock()
        instance_result.scalar_one_or_none.return_value = instance
        db = SimpleNamespace(
            execute=AsyncMock(side_effect=[priv_result, instance_result]),
            commit=AsyncMock(),
        )

        with pytest.raises(AppException) as exc_info:
            await QueryPrivService.revoke_privilege(
                db,
                priv_id=9,
                operator={
                    "id": 8,
                    "permissions": ["query_mgtpriv"],
                    "resource_groups": [3],
                    "is_superuser": False,
                },
            )

        assert exc_info.value.message == "您没有权限撤销该查询权限"
        assert priv.is_deleted == 0
        db.commit.assert_not_awaited()


class TestManagerResolution:
    @pytest.mark.asyncio
    async def test_resolve_manager_prefers_username(self):
        db = AsyncMock()
        username_result = MagicMock()
        username_result.scalar_one_or_none.return_value = 52
        db.execute = AsyncMock(return_value=username_result)

        manager_id = await UserService._resolve_manager_id(db, "leader01", "")

        assert manager_id == 52

    @pytest.mark.asyncio
    async def test_resolve_manager_falls_back_to_unique_display_name(self):
        db = AsyncMock()
        username_result = MagicMock()
        username_result.scalar_one_or_none.return_value = None
        display_result = MagicMock()
        display_result.scalars.return_value.all.return_value = [88]
        db.execute = AsyncMock(side_effect=[username_result, display_result])

        manager_id = await UserService._resolve_manager_id(db, "missing-user", "张经理")

        assert manager_id == 88

    @pytest.mark.asyncio
    async def test_resolve_manager_rejects_duplicate_display_name(self):
        db = AsyncMock()
        display_result = MagicMock()
        display_result.scalars.return_value.all.return_value = [7, 9]
        db.execute = AsyncMock(return_value=display_result)

        with pytest.raises(AppException) as exc_info:
            await UserService._resolve_manager_id(db, "", "同名经理")

        assert "匹配到多个用户" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_resolve_manager_requires_valid_username_or_display_name(self):
        db = AsyncMock()
        username_result = MagicMock()
        username_result.scalar_one_or_none.return_value = None
        display_result = MagicMock()
        display_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[username_result, display_result])

        with pytest.raises(AppException) as exc_info:
            await UserService._resolve_manager_id(db, "ghost", "未知主管")

        assert "直属上级不存在" in exc_info.value.message


class TestOracleSchemaDiscovery:
    @pytest.mark.asyncio
    async def test_oracle_prefers_dba_users_for_privileged_account(self):
        engine = OracleEngine.__new__(OracleEngine)

        def fake_run_query_sync(self, sql: str, params=None):
            assert "FROM dba_users" in sql
            return ResultSet(rows=[("PDBADMIN",), ("SAGITTA",)])

        engine._run_query_sync = MethodType(fake_run_query_sync, engine)

        rs = await engine.get_all_databases()

        assert rs.is_success
        assert rs.rows == [("PDBADMIN",), ("SAGITTA",)]

    @pytest.mark.asyncio
    async def test_oracle_falls_back_to_current_user_schema_only(self):
        engine = OracleEngine.__new__(OracleEngine)
        calls: list[str] = []

        def fake_run_query_sync(self, sql: str, params=None):
            calls.append(" ".join(sql.split()))
            if "FROM dba_users" in sql:
                return ResultSet(error="ORA-00942: table or view does not exist")
            assert "FROM user_users" in sql
            assert "ALL_USERS" not in sql
            return ResultSet(rows=[("SAGITTA",)])

        engine._run_query_sync = MethodType(fake_run_query_sync, engine)

        rs = await engine.get_all_databases()

        assert rs.is_success
        assert rs.rows == [("SAGITTA",)]
        assert len(calls) == 2
