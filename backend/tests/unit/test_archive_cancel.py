import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.archive import ArchiveJobStatus
from app.models.workflow import AuditStatus, WorkflowStatus
from app.services.archive import ArchiveService


@pytest.mark.asyncio
async def test_archive_application_can_cancel_before_node_operates():
    job = SimpleNamespace(
        status=ArchiveJobStatus.PENDING_REVIEW,
        workflow_id=42,
        created_by_id=7,
    )
    workflow = SimpleNamespace(status=WorkflowStatus.PENDING_REVIEW, engineer="liuyang")
    audit = SimpleNamespace(
        audit_auth_groups_info=json.dumps(
            [{"node_name": "直属领导", "status": AuditStatus.PENDING, "operator": None}],
            ensure_ascii=False,
        )
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = audit
    db = SimpleNamespace(
        get=AsyncMock(return_value=workflow),
        execute=AsyncMock(return_value=result),
    )

    can_cancel = await ArchiveService.can_cancel_application(
        db,
        job,
        {"id": 7, "username": "liuyang", "is_superuser": False},
    )

    assert can_cancel is True


@pytest.mark.asyncio
async def test_archive_application_cannot_cancel_after_node_operates():
    job = SimpleNamespace(
        status=ArchiveJobStatus.PENDING_REVIEW,
        workflow_id=42,
        created_by_id=7,
    )
    workflow = SimpleNamespace(status=WorkflowStatus.PENDING_REVIEW, engineer="liuyang")
    audit = SimpleNamespace(
        audit_auth_groups_info=json.dumps(
            [{"node_name": "直属领导", "status": AuditStatus.PASSED, "operator": "yanjiabao"}],
            ensure_ascii=False,
        )
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = audit
    db = SimpleNamespace(
        get=AsyncMock(return_value=workflow),
        execute=AsyncMock(return_value=result),
    )

    can_cancel = await ArchiveService.can_cancel_application(
        db,
        job,
        {"id": 7, "username": "liuyang", "is_superuser": False},
    )

    assert can_cancel is False


@pytest.mark.asyncio
async def test_archive_applicant_cannot_control_after_approval_without_execute_permission():
    job = SimpleNamespace(
        id=13,
        status=ArchiveJobStatus.APPROVED,
        workflow_id=42,
        source_instance_id=8,
        created_by_id=7,
    )
    db = SimpleNamespace()

    with patch("app.services.archive.ArchiveService.get_job_obj", AsyncMock(return_value=job)), patch(
        "app.services.archive.ArchiveService._load_instance",
        AsyncMock(return_value=SimpleNamespace(resource_groups=[])),
    ), pytest.raises(Exception) as exc_info:
        await ArchiveService.set_job_control_state(
            db,
            13,
            "cancel",
            {"id": 7, "username": "wanglei", "permissions": ["archive_apply"], "is_superuser": False},
        )

    assert "没有归档执行权限" in str(exc_info.value)


@pytest.mark.asyncio
async def test_archive_execute_permission_can_schedule_job_and_sync_workflow():
    scheduled_at = datetime.now(UTC) + timedelta(hours=1)
    job = SimpleNamespace(
        id=13,
        status=ArchiveJobStatus.APPROVED,
        workflow_id=42,
        source_instance_id=8,
        finished_at=None,
    )
    wf = SimpleNamespace(
        id=42,
        execute_mode=None,
        executed_by_id=None,
        executed_by_name=None,
        scheduled_execute_at=None,
        external_executed_at=None,
        external_result_status=None,
        external_result_remark=None,
        status=WorkflowStatus.REVIEW_PASS,
    )
    audit_result = MagicMock()
    audit_result.scalar_one_or_none.return_value = None
    db = SimpleNamespace(
        get=AsyncMock(return_value=wf),
        execute=AsyncMock(return_value=audit_result),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    data = SimpleNamespace(mode="scheduled", scheduled_at=scheduled_at, timing_time=None)

    with patch("app.services.archive.ArchiveService.get_job_obj", AsyncMock(return_value=job)), patch(
        "app.services.archive.ArchiveService._load_instance",
        AsyncMock(return_value=SimpleNamespace(resource_groups=[])),
    ):
        result = await ArchiveService.start_job(
            db,
            13,
            {"id": 2, "username": "lijialin", "permissions": ["archive_execute"], "role": "dba", "is_superuser": False},
            data,
        )

    assert result["status"] == ArchiveJobStatus.SCHEDULED
    assert job.status == ArchiveJobStatus.SCHEDULED
    assert wf.execute_mode == "scheduled"
    assert wf.status == WorkflowStatus.TIMING_TASK
    assert wf.executed_by_name == "lijialin"


@pytest.mark.asyncio
async def test_archive_job_visible_to_current_manager_approver():
    job = SimpleNamespace(
        id=13,
        workflow_id=42,
        created_by_id=7,
    )
    db = SimpleNamespace()

    with patch(
        "app.services.archive.AuditService.get_pending_workflow_ids_for_user",
        AsyncMock(return_value={42}),
    ), patch(
        "app.services.archive.AuditService.get_audited_workflow_ids_for_user",
        AsyncMock(return_value=set()),
    ):
        can_view = await ArchiveService.can_view_job(
            db,
            job,
            {"id": 9, "username": "leader", "permissions": [], "is_superuser": False},
        )

    assert can_view is True


@pytest.mark.asyncio
async def test_archive_job_not_visible_to_unrelated_user_without_archive_permissions():
    job = SimpleNamespace(
        id=13,
        workflow_id=42,
        created_by_id=7,
    )
    db = SimpleNamespace()

    with patch(
        "app.services.archive.AuditService.get_pending_workflow_ids_for_user",
        AsyncMock(return_value=set()),
    ), patch(
        "app.services.archive.AuditService.get_audited_workflow_ids_for_user",
        AsyncMock(return_value=set()),
    ):
        can_view = await ArchiveService.can_view_job(
            db,
            job,
            {"id": 10, "username": "other", "permissions": [], "is_superuser": False},
        )

    assert can_view is False
