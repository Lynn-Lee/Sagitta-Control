"""
工单服务单元测试（Pack G）。
覆盖状态流转、格式化、SQL 校验逻辑（通过 mock 避免真实 DB 依赖）。
"""
import json
from datetime import UTC, datetime
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


class TestWorkflowHelpers:
    def test_build_audit_chain_text_uses_node_names_while_pending(self):
        nodes = [
            {"order": 1, "node_name": "直属领导审批", "status": 1},
            {"order": 2, "node_name": "资源组 DBA 审批", "status": 0},
        ]

        result = WorkflowService._build_audit_chain_text(
            nodes,
            WorkflowStatus.PENDING_REVIEW,
        )

        assert result == "直属领导审批 -> 资源组 DBA 审批"

    def test_build_audit_chain_text_uses_operator_display_names_after_review(self):
        nodes = [
            {"order": 1, "node_name": "直属领导审批", "operator": "leader_1"},
            {"order": 2, "node_name": "资源组 DBA 审批", "operator": "dba_1"},
        ]

        result = WorkflowService._build_audit_chain_text(
            nodes,
            WorkflowStatus.FINISH,
            {"leader_1": "直属领导", "dba_1": "资源组 DBA"},
        )

        assert result == "直属领导 -> 资源组 DBA"

    def test_build_audit_chain_text_returns_dash_when_no_operator_finished(self):
        result = WorkflowService._build_audit_chain_text(
            [{"order": 1, "node_name": "直属领导审批"}],
            WorkflowStatus.FINISH,
        )
        assert result == "—"

    def test_get_current_node_name_only_for_pending_review(self):
        nodes = [{"node_name": "第 1 级审批", "status": 0}]

        assert WorkflowService._get_current_node_name(nodes, WorkflowStatus.PENDING_REVIEW) == "第 1 级审批"
        assert WorkflowService._get_current_node_name(nodes, WorkflowStatus.FINISH) == "—"

    def test_decorate_snapshot_for_applicant_only_applies_to_manager_nodes(self):
        nodes_snapshot = [
            {"order": 1, "approver_type": "manager", "node_name": "直属领导审批"},
            {"order": 2, "approver_type": "users", "node_name": "指定人员审批"},
        ]

        decorated = WorkflowService._decorate_snapshot_for_applicant(
            nodes_snapshot,
            {"id": 7, "username": "liuyang", "display_name": "刘洋"},
        )

        assert decorated[0]["applicant_id"] == 7
        assert decorated[0]["applicant_name"] == "刘洋"
        assert "applicant_id" not in decorated[1]


class TestWorkflowListingAndDetail:
    def _make_workflow(self, **overrides):
        wf = SimpleNamespace(
            id=5,
            workflow_name="删除线上错误数据",
            group_id=1,
            group_name="技术组",
            instance_id=8,
            db_name="ump_testdb",
            syntax_type=2,
            is_backup=True,
            engineer="00311624",
            engineer_display="刘洋",
            status=WorkflowStatus.PENDING_REVIEW,
            audit_auth_groups="1",
            run_date_start=None,
            run_date_end=None,
            finish_time=None,
            created_at=datetime(2026, 4, 18, tzinfo=UTC),
            content=None,
        )
        for key, value in overrides.items():
            setattr(wf, key, value)
        return wf

    @pytest.mark.asyncio
    async def test_list_workflows_audit_view_formats_current_node_and_chain(self):
        db = AsyncMock()
        wf = self._make_workflow()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        data_result = MagicMock()
        data_result.all.return_value = [(wf, "MySQL-技术组")]
        audit_nodes = [
            {"order": 1, "node_name": "直属领导审批", "status": 0, "operator": "yanjiabao"},
            {"order": 2, "node_name": "资源组 DBA 审批", "status": 0},
        ]
        audit_result = MagicMock()
        audit_result.scalars.return_value.all.return_value = [
            SimpleNamespace(workflow_id=5, audit_auth_groups_info=json.dumps(audit_nodes, ensure_ascii=False))
        ]
        user_result = MagicMock()
        user_result.all.return_value = [("yanjiabao", "闫家宝")]
        db.execute = AsyncMock(side_effect=[count_result, data_result, audit_result, user_result])

        with patch("app.services.audit.AuditService.get_pending_workflow_ids_for_user", AsyncMock(return_value={5})), patch(
            "app.services.audit.AuditService.get_audited_workflow_ids_for_user",
            AsyncMock(return_value=set()),
        ):
            total, items, scope = await WorkflowService.list_workflows(
                db,
                {"id": 2, "username": "yanjiabao", "is_superuser": False},
                view="audit",
            )

        assert total == 1
        assert scope is None
        assert items[0]["instance_name"] == "MySQL-技术组"
        assert items[0]["current_node_name"] == "直属领导审批"
        assert items[0]["audit_chain_text"] == "直属领导审批 -> 资源组 DBA 审批"

    @pytest.mark.asyncio
    async def test_get_detail_sets_can_audit_for_current_approver(self):
        db = AsyncMock()
        wf = self._make_workflow(content=SimpleNamespace(sql_content="delete from t", review_content="[]", execute_result=""))
        row_result = MagicMock()
        row_result.first.return_value = (wf, "MySQL-技术组")
        db.execute = AsyncMock(return_value=row_result)
        audit_info = {
            "nodes": [
                {"order": 1, "node_name": "直属领导审批", "status": 0, "approver_type": "manager"},
            ]
        }

        with patch("app.services.audit.AuditService.get_audit_info", AsyncMock(return_value=audit_info)), patch(
            "app.services.audit.AuditService.get_audit_logs", AsyncMock(return_value=[])
        ), patch(
            "app.services.audit.AuditService._check_approver_permission", AsyncMock(return_value=None)
        ):
            detail = await WorkflowService.get_detail(
                db,
                5,
                {"id": 2, "username": "yanjiabao", "permissions": [], "is_superuser": False},
            )

        assert detail["sql_content"] == "delete from t"
        assert detail["can_audit"] is True
        assert detail["can_execute"] is False
        assert detail["can_cancel"] is False

    @pytest.mark.asyncio
    async def test_get_detail_allows_engineer_to_cancel_before_finish(self):
        db = AsyncMock()
        wf = self._make_workflow(
            engineer="liuyang",
            status=WorkflowStatus.TIMING_TASK,
            content=SimpleNamespace(sql_content="delete from t", review_content="[]", execute_result=""),
        )
        row_result = MagicMock()
        row_result.first.return_value = (wf, "MySQL-技术组")
        db.execute = AsyncMock(return_value=row_result)

        with patch("app.services.audit.AuditService.get_audit_info", AsyncMock(return_value={"nodes": []})), patch(
            "app.services.audit.AuditService.get_audit_logs", AsyncMock(return_value=[])
        ):
            detail = await WorkflowService.get_detail(
                db,
                5,
                {"id": 7, "username": "liuyang", "permissions": [], "is_superuser": False},
            )

        assert detail["can_audit"] is False
        assert detail["can_cancel"] is True


class TestWorkflowExecuteSync:
    @pytest.mark.asyncio
    async def test_execute_sync_marks_missing_instance_as_exception(self):
        db = AsyncMock()
        wf = SimpleNamespace(
            id=10,
            instance_id=8,
            db_name="ump_testdb",
            content=SimpleNamespace(sql_content="delete from t", execute_result=None),
            status=WorkflowStatus.REVIEW_PASS,
            finish_time=None,
        )
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)

        await WorkflowService._execute_sync(db, wf, {"id": 1, "username": "admin"})

        assert wf.status == WorkflowStatus.EXCEPTION
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_sync_success_writes_finish_status_and_log(self):
        db = AsyncMock()
        wf = SimpleNamespace(
            id=10,
            instance_id=8,
            db_name="ump_testdb",
            content=SimpleNamespace(sql_content="delete from t", execute_result=None),
            status=WorkflowStatus.REVIEW_PASS,
            finish_time=None,
        )
        instance = SimpleNamespace(id=8)
        audit = SimpleNamespace(id=99)
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=instance)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=audit)),
            ]
        )
        engine = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(error="")))

        with patch("app.services.workflow.get_engine", return_value=engine), patch(
            "app.services.workflow.AuditService._write_log",
            AsyncMock(),
        ) as write_log_mock:
            await WorkflowService._execute_sync(db, wf, {"id": 1, "username": "admin"})

        assert wf.status == WorkflowStatus.FINISH
        assert wf.finish_time is not None
        assert wf.content.execute_result == '{"success": true, "error": ""}'
        assert db.commit.await_count == 2
        write_log_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_sync_records_engine_errors(self):
        db = AsyncMock()
        wf = SimpleNamespace(
            id=10,
            instance_id=8,
            db_name="ump_testdb",
            content=SimpleNamespace(sql_content="delete from t", execute_result=None),
            status=WorkflowStatus.REVIEW_PASS,
            finish_time=None,
        )
        instance = SimpleNamespace(id=8)
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=instance)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            ]
        )
        engine = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("exec failed")))

        with patch("app.services.workflow.get_engine", return_value=engine):
            await WorkflowService._execute_sync(db, wf, {"id": 1, "username": "admin"})

        assert wf.status == WorkflowStatus.EXCEPTION
        assert wf.finish_time is not None
        assert wf.content.execute_result == '{"error": "exec failed"}'
        assert db.commit.await_count == 2


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
