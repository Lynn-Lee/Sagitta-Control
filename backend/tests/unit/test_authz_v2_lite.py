"""
v2-lite 权限体系单元测试。
"""

from types import MethodType
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppException
from app.engines.models import ResultSet
from app.engines.oracle import OracleEngine
from app.schemas.approval_flow import ApprovalFlowNodeCreate
from app.schemas.query import PrivApplyRequest
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


class TestQueryPrivilegeHelpers:
    def test_table_scope_normalizes_to_table_priv(self):
        assert QueryPrivService._normalize_scope_type("table", "") == ("table", 2)

    def test_table_name_also_forces_table_scope(self):
        assert QueryPrivService._normalize_scope_type("database", "orders") == ("table", 2)

    def test_database_scope_normalizes_to_database_priv(self):
        assert QueryPrivService._normalize_scope_type("database", "") == ("database", 1)


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
    async def test_oracle_falls_back_to_current_user_visible_owners_only(self):
        engine = OracleEngine.__new__(OracleEngine)
        calls: list[str] = []

        def fake_run_query_sync(self, sql: str, params=None):
            calls.append(" ".join(sql.split()))
            if "FROM dba_users" in sql:
                return ResultSet(error="ORA-00942: table or view does not exist")
            assert "FROM user_users" in sql
            assert "FROM all_tables" in sql
            assert "ALL_USERS" not in sql
            return ResultSet(rows=[("SAGITTA",), ("APP_AUDIT",)])

        engine._run_query_sync = MethodType(fake_run_query_sync, engine)

        rs = await engine.get_all_databases()

        assert rs.is_success
        assert rs.rows == [("SAGITTA",), ("APP_AUDIT",)]
        assert len(calls) == 2
