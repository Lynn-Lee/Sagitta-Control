"""
工单服务单元测试（Pack G）。
覆盖状态流转、格式化、SQL 校验逻辑（通过 mock 避免真实 DB 依赖）。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import AppException
from app.models.workflow import AuditStatus, WorkflowStatus, WorkflowType
from app.schemas.workflow import WorkflowCreateRequest
from app.services.workflow import WorkflowService


class TestWorkflowStatus:
    """验证工单状态枚举值（修复 1.x 字符串状态混乱 P1-1）。"""

    def test_pending_review_is_zero(self):
        assert WorkflowStatus.PENDING_REVIEW == 0

    def test_finish_is_six(self):
        assert WorkflowStatus.FINISH == 6

    def test_exception_is_seven(self):
        assert WorkflowStatus.EXCEPTION == 7

    def test_abort_is_eight(self):
        assert WorkflowStatus.ABORT == 8

    def test_all_statuses_unique(self):
        values = [s.value for s in WorkflowStatus]
        assert len(values) == len(set(values))

    def test_int_comparison_works(self):
        """整数枚举应与整数直接可比（替代 1.x 字符串比较）。"""
        assert WorkflowStatus.PENDING_REVIEW == 0
        assert WorkflowStatus.PENDING_REVIEW == 0
        assert WorkflowStatus.FINISH != WorkflowStatus.EXCEPTION


class TestAuditStatus:
    def test_pending_is_zero(self):
        assert AuditStatus.PENDING == 0

    def test_passed_is_one(self):
        assert AuditStatus.PASSED == 1

    def test_rejected_is_two(self):
        assert AuditStatus.REJECTED == 2


class TestWorkflowType:
    def test_query_type(self):
        assert WorkflowType.QUERY == 1

    def test_sql_type(self):
        assert WorkflowType.SQL == 2


class TestFmtWorkflow:
    """验证工单格式化方法。"""

    def _make_workflow(self, **overrides):
        """构造 mock SqlWorkflow 对象。"""
        from datetime import datetime
        wf = MagicMock()
        wf.id = 1
        wf.workflow_name = "测试工单"
        wf.status = WorkflowStatus.PENDING_REVIEW
        wf.engineer = "testuser"
        wf.engineer_display = "测试用户"
        wf.group_id = 1
        wf.group_name = "运维组"
        wf.instance_id = 10
        wf.db_name = "test_db"
        wf.syntax_type = 2  # DML
        wf.is_backup = True
        wf.audit_auth_groups = ""
        wf.run_date_start = None
        wf.run_date_end = None
        wf.finish_time = None
        wf.export_format = None
        wf.created_at = datetime(2026, 1, 1)
        wf.updated_at = datetime(2026, 1, 1)
        wf.tenant_id = 1
        for k, v in overrides.items():
            setattr(wf, k, v)
        return wf

    def test_fmt_workflow_contains_id(self):
        wf = self._make_workflow()
        result = WorkflowService._fmt_workflow(wf, "mysql-prod")
        assert result["id"] == 1

    def test_fmt_workflow_contains_status(self):
        wf = self._make_workflow(status=WorkflowStatus.FINISH)
        result = WorkflowService._fmt_workflow(wf, "mysql-prod")
        assert result["status"] == WorkflowStatus.FINISH

    def test_fmt_workflow_contains_engineer(self):
        wf = self._make_workflow()
        result = WorkflowService._fmt_workflow(wf, "")
        assert result["engineer"] == "testuser"

    def test_fmt_workflow_returns_dict(self):
        wf = self._make_workflow()
        result = WorkflowService._fmt_workflow(wf, "db-instance")
        assert isinstance(result, dict)
        required_keys = {"id", "workflow_name", "status", "engineer", "db_name"}
        assert required_keys.issubset(result.keys())

    def test_fmt_workflow_instance_name_included(self):
        wf = self._make_workflow()
        result = WorkflowService._fmt_workflow(wf, "my-mysql-instance")
        assert result.get("instance_name") == "my-mysql-instance"


class TestCheckSql:
    """验证 SQL 预检查（sqlglot 静态分析，替代 goInception）。"""

    @pytest.mark.asyncio
    async def test_check_sql_select_allowed(self):
        """纯 SELECT 应该通过检查（工单中不允许 SELECT，但 check 本身不报错）。"""
        mock_db = AsyncMock()
        mock_instance = MagicMock()
        mock_instance.db_type = "mysql"
        mock_instance.host = "127.0.0.1"

        # DB 查询返回 mock instance
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_instance
        mock_db.execute = AsyncMock(return_value=mock_result)

        # get_engine 会尝试连接，mock 掉
        mock_engine = MagicMock()
        mock_engine.execute_check = AsyncMock(return_value=MagicMock(rows=[], column_list=[]))
        with patch("app.services.workflow.get_engine", return_value=mock_engine):
            result = await WorkflowService.check_sql(
                db=mock_db,
                instance_id=1,
                db_name="test",
                sql_content="SELECT * FROM users;",
            )
        # 返回检查结果（列表）
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_check_sql_instance_not_found_raises(self):
        """实例不存在时应抛出异常。"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(Exception):  # noqa: B017
            await WorkflowService.check_sql(
                db=mock_db,
                instance_id=99999,
                db_name="test",
                sql_content="SELECT 1;",
            )

    @pytest.mark.asyncio
    async def test_check_sql_ddl_returns_result(self):
        """DDL 语句应该返回检查结果。"""
        mock_db = AsyncMock()
        mock_instance = MagicMock()
        mock_instance.db_type = "mysql"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_instance
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_engine = MagicMock()
        mock_engine.execute_check = AsyncMock(return_value=MagicMock(rows=[], column_list=[]))
        with patch("app.services.workflow.get_engine", return_value=mock_engine):
            result = await WorkflowService.check_sql(
                db=mock_db,
                instance_id=1,
                db_name="test",
                sql_content="CREATE TABLE t (id INT PRIMARY KEY);",
            )
        assert isinstance(result, list)


class TestPendingForMe:
    """验证「待我审批」查询逻辑。"""

    @pytest.mark.asyncio
    async def test_pending_for_me_returns_tuple(self):
        """应返回 (total, list) 元组。"""
        mock_db = AsyncMock()
        mock_user = {"id": 1, "username": "testuser", "is_superuser": False}

        # 模拟 count 查询
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        # 模拟 items 查询
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[count_result, items_result])

        total, items = await WorkflowService.pending_for_me(
            db=mock_db,
            user=mock_user,
        )
        assert isinstance(total, int)
        assert isinstance(items, list)


class TestCreateWorkflow:
    def _request(self, **overrides):
        payload = {
            "workflow_name": "站点库变更",
            "group_id": None,
            "instance_id": 100,
            "db_name": "site_db",
            "sql_content": "UPDATE orders SET status = 1 WHERE id = 1;",
            "syntax_type": 2,
            "is_backup": True,
            "flow_id": 11,
        }
        payload.update(overrides)
        return WorkflowCreateRequest(**payload)

    @pytest.mark.asyncio
    async def test_create_uses_intersection_resource_group(self):
        db = AsyncMock()
        instance = SimpleNamespace(
            resource_groups=[
                SimpleNamespace(id=2, group_name="研发资源组", is_active=True),
                SimpleNamespace(id=9, group_name="停用资源组", is_active=False),
            ]
        )
        result = MagicMock()
        result.scalar_one_or_none.return_value = instance
        db.execute = AsyncMock(return_value=result)
        db.flush = AsyncMock()
        db.add = MagicMock()

        review_set = SimpleNamespace(rows=[], error_count=0, error=False)
        mock_engine = MagicMock()
        mock_engine.execute_check = AsyncMock(return_value=review_set)
        audit_service = MagicMock()
        audit_service.create_audit = AsyncMock()
        nodes_snapshot = [{"order": 1, "node_id": 11, "node_name": "直属上级", "approver_type": "manager"}]

        operator = {"id": 7, "username": "dev1", "display_name": "研发一号", "resource_groups": [2, 5]}

        with patch("app.services.workflow.get_engine", return_value=mock_engine), patch(
            "app.services.workflow.AuditService", return_value=audit_service
        ), patch(
            "app.services.approval_flow.ApprovalFlowService.snapshot_for_workflow",
            AsyncMock(return_value=nodes_snapshot),
        ):
            workflow = await WorkflowService.create(db, self._request(), operator)

        assert workflow.group_id == 2
        assert workflow.group_name == "研发资源组"
        assert workflow.audit_auth_groups == "2"
        audit_service.create_audit.assert_awaited_once()
        passed_snapshot = audit_service.create_audit.await_args.kwargs["nodes_snapshot"]
        assert passed_snapshot[0]["applicant_id"] == 7
        assert passed_snapshot[0]["applicant_name"] == "研发一号"

    @pytest.mark.asyncio
    async def test_create_rejects_explicit_group_outside_scope(self):
        db = AsyncMock()
        instance = SimpleNamespace(
            resource_groups=[SimpleNamespace(id=2, group_name="研发资源组", is_active=True)]
        )
        result = MagicMock()
        result.scalar_one_or_none.return_value = instance
        db.execute = AsyncMock(return_value=result)

        operator = {"id": 7, "username": "dev1", "display_name": "研发一号", "resource_groups": [2]}

        with pytest.raises(AppException) as exc_info:
            await WorkflowService.create(db, self._request(group_id=8), operator)

        assert exc_info.value.code == 400
        assert "所选资源组不在你的实例访问范围内" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_create_rejects_instance_outside_resource_scope(self):
        db = AsyncMock()
        instance = SimpleNamespace(
            resource_groups=[SimpleNamespace(id=9, group_name="DBA资源组", is_active=True)]
        )
        result = MagicMock()
        result.scalar_one_or_none.return_value = instance
        db.execute = AsyncMock(return_value=result)

        operator = {"id": 7, "username": "dev1", "display_name": "研发一号", "resource_groups": [2]}

        with pytest.raises(AppException) as exc_info:
            await WorkflowService.create(db, self._request(), operator)

        assert exc_info.value.code == 403
        assert "目标实例不在你的资源组访问范围内" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_create_requires_approval_flow(self):
        with pytest.raises(AppException) as exc_info:
            await WorkflowService.create(
                AsyncMock(),
                self._request(flow_id=None),
                {"id": 7, "username": "dev1", "display_name": "研发一号", "resource_groups": [2]},
            )

        assert exc_info.value.message == "请选择审批流"
