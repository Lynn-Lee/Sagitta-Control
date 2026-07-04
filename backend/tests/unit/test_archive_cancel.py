import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import AppException
from app.models.archive import ArchiveBatchStatus, ArchiveJobStatus
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
@pytest.mark.parametrize("initial_status", [ArchiveJobStatus.QUEUED, ArchiveJobStatus.RUNNING])
async def test_archive_execute_permission_can_pause_active_job(initial_status):
    job = SimpleNamespace(
        id=13,
        status=initial_status,
        workflow_id=42,
        source_instance_id=8,
        finished_at=None,
    )
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())

    with patch("app.services.archive.ArchiveService.get_job_obj", AsyncMock(return_value=job)), patch(
        "app.services.archive.ArchiveService._load_instance",
        AsyncMock(return_value=SimpleNamespace(resource_groups=[])),
    ):
        result = await ArchiveService.set_job_control_state(
            db,
            13,
            "pause",
            {"id": 2, "username": "lijialin", "permissions": ["archive_execute"], "role": "dba", "is_superuser": False},
        )

    assert result.status == ArchiveJobStatus.PAUSING
    assert job.finished_at is None
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(job)


@pytest.mark.asyncio
async def test_archive_execute_permission_can_resume_paused_job():
    job = SimpleNamespace(
        id=13,
        status=ArchiveJobStatus.PAUSED,
        workflow_id=42,
        source_instance_id=8,
        finished_at=None,
    )
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())

    with patch("app.services.archive.ArchiveService.get_job_obj", AsyncMock(return_value=job)), patch(
        "app.services.archive.ArchiveService._load_instance",
        AsyncMock(return_value=SimpleNamespace(resource_groups=[])),
    ):
        result = await ArchiveService.set_job_control_state(
            db,
            13,
            "resume",
            {"id": 2, "username": "lijialin", "permissions": ["archive_execute"], "role": "dba", "is_superuser": False},
        )

    assert result.status == ArchiveJobStatus.QUEUED
    assert job.finished_at is None
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(job)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("initial_status", "workflow_status"),
    [
        (ArchiveJobStatus.APPROVED, WorkflowStatus.REVIEW_PASS),
        (ArchiveJobStatus.SCHEDULED, WorkflowStatus.TIMING_TASK),
        (ArchiveJobStatus.QUEUED, WorkflowStatus.QUEUING),
        (ArchiveJobStatus.PAUSED, WorkflowStatus.QUEUING),
    ],
)
async def test_archive_execute_permission_can_cancel_not_running_jobs(initial_status, workflow_status):
    job = SimpleNamespace(
        id=13,
        status=initial_status,
        workflow_id=42,
        source_instance_id=8,
        finished_at=None,
    )
    wf = SimpleNamespace(status=workflow_status)
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock(), get=AsyncMock(return_value=wf))

    with patch("app.services.archive.ArchiveService.get_job_obj", AsyncMock(return_value=job)), patch(
        "app.services.archive.ArchiveService._load_instance",
        AsyncMock(return_value=SimpleNamespace(resource_groups=[])),
    ):
        result = await ArchiveService.set_job_control_state(
            db,
            13,
            "cancel",
            {"id": 2, "username": "lijialin", "permissions": ["archive_execute"], "role": "dba", "is_superuser": False},
        )

    assert result.status == ArchiveJobStatus.CANCELED
    assert job.finished_at is not None
    assert wf.status == WorkflowStatus.ABORT
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(job)


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_status", [ArchiveJobStatus.RUNNING, ArchiveJobStatus.PAUSING])
async def test_archive_execute_permission_marks_active_cancel_as_canceling(initial_status):
    job = SimpleNamespace(
        id=13,
        status=initial_status,
        workflow_id=42,
        source_instance_id=8,
        finished_at=None,
    )
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock(), get=AsyncMock())

    with patch("app.services.archive.ArchiveService.get_job_obj", AsyncMock(return_value=job)), patch(
        "app.services.archive.ArchiveService._load_instance",
        AsyncMock(return_value=SimpleNamespace(resource_groups=[])),
    ):
        result = await ArchiveService.set_job_control_state(
            db,
            13,
            "cancel",
            {"id": 2, "username": "lijialin", "permissions": ["archive_execute"], "role": "dba", "is_superuser": False},
        )

    assert result.status == ArchiveJobStatus.CANCELING
    assert job.finished_at is None
    db.get.assert_not_called()
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(job)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "initial_status", "message"),
    [
        ("pause", ArchiveJobStatus.APPROVED, "只有队列中或执行中的作业可以暂停"),
        ("resume", ArchiveJobStatus.RUNNING, "只有已暂停的作业可以继续"),
        ("cancel", ArchiveJobStatus.SUCCESS, "当前作业状态不能取消"),
        ("cancel", ArchiveJobStatus.FAILED, "当前作业状态不能取消"),
        ("cancel", ArchiveJobStatus.CANCELED, "当前作业状态不能取消"),
        ("cancel", ArchiveJobStatus.CANCELING, "当前作业状态不能取消"),
    ],
)
async def test_archive_control_rejects_invalid_state_transitions(action, initial_status, message):
    job = SimpleNamespace(
        id=13,
        status=initial_status,
        workflow_id=42,
        source_instance_id=8,
        finished_at=None,
    )
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())

    with patch("app.services.archive.ArchiveService.get_job_obj", AsyncMock(return_value=job)), patch(
        "app.services.archive.ArchiveService._load_instance",
        AsyncMock(return_value=SimpleNamespace(resource_groups=[])),
    ), pytest.raises(AppException) as exc_info:
        await ArchiveService.set_job_control_state(
            db,
            13,
            action,
            {"id": 2, "username": "lijialin", "permissions": ["archive_execute"], "role": "dba", "is_superuser": False},
        )

    assert message in str(exc_info.value)
    db.commit.assert_not_called()
    db.refresh.assert_not_called()


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
async def test_archive_execute_job_success_syncs_workflow_finish_and_content():
    finished_at = datetime.now(UTC)
    job = SimpleNamespace(
        id=13,
        status=ArchiveJobStatus.QUEUED,
        archive_mode="purge",
        workflow_id=42,
        source_instance_id=8,
        source_db="testdb",
        source_table="orders",
        created_by_id=7,
        created_by="liuyang",
        started_at=None,
        finished_at=None,
        processed_rows=0,
        current_batch=0,
        error_message="",
    )
    content = SimpleNamespace(execute_result="")
    wf = SimpleNamespace(
        id=42,
        status=WorkflowStatus.QUEUING,
        execute_mode="immediate",
        finish_time=None,
        content=content,
    )
    workflow_result = MagicMock()
    workflow_result.scalar_one_or_none.return_value = wf
    db = SimpleNamespace(
        get=AsyncMock(return_value=wf),
        execute=AsyncMock(return_value=workflow_result),
        commit=AsyncMock(),
    )

    async def finish_job(_db, archive_job):
        archive_job.status = ArchiveJobStatus.SUCCESS
        archive_job.finished_at = finished_at
        archive_job.processed_rows = 3
        archive_job.current_batch = 1
        await _db.commit()

    with patch("app.services.archive.ArchiveService.get_job_obj", AsyncMock(return_value=job)), patch(
        "app.services.archive.ArchiveService._execute_purge_job",
        side_effect=finish_job,
    ), patch("app.services.notify.NotifyService.enqueue_event"):
        await ArchiveService.execute_job(db, 13, 2)

    assert wf.status == WorkflowStatus.FINISH
    assert wf.finish_time == finished_at
    execute_result = json.loads(content.execute_result)
    assert execute_result["success"] is True
    assert execute_result["status"] == ArchiveJobStatus.SUCCESS
    assert execute_result["processed_rows"] == 3
    assert execute_result["current_batch"] == 1


@pytest.mark.asyncio
async def test_archive_execute_job_pause_does_not_mark_workflow_exception():
    job = SimpleNamespace(
        id=13,
        status=ArchiveJobStatus.QUEUED,
        archive_mode="purge",
        workflow_id=42,
        source_instance_id=8,
        source_db="testdb",
        source_table="orders",
        created_by_id=7,
        created_by="liuyang",
        started_at=None,
        finished_at=None,
        processed_rows=100,
        current_batch=1,
        error_message="",
    )
    content = SimpleNamespace(execute_result="")
    wf = SimpleNamespace(
        id=42,
        status=WorkflowStatus.QUEUING,
        execute_mode="immediate",
        finish_time=None,
        content=content,
    )
    workflow_result = MagicMock()
    workflow_result.scalar_one_or_none.return_value = wf
    db = SimpleNamespace(
        get=AsyncMock(return_value=wf),
        execute=AsyncMock(return_value=workflow_result),
        commit=AsyncMock(),
    )

    async def pause_job(_db, archive_job):
        archive_job.status = ArchiveJobStatus.PAUSED
        archive_job.finished_at = None
        await _db.commit()

    with patch("app.services.archive.ArchiveService.get_job_obj", AsyncMock(return_value=job)), patch(
        "app.services.archive.ArchiveService._execute_purge_job",
        side_effect=pause_job,
    ), patch("app.services.notify.NotifyService.enqueue_event") as enqueue_event:
        await ArchiveService.execute_job(db, 13, 2)

    assert job.status == ArchiveJobStatus.PAUSED
    assert wf.status == WorkflowStatus.EXECUTING
    assert wf.finish_time is None
    assert content.execute_result == ""
    assert [call.args[0]["event_type"] for call in enqueue_event.call_args_list] == ["execution_started"]


@pytest.mark.asyncio
async def test_archive_dest_mongo_rejects_partial_source_delete_after_insert():
    job = SimpleNamespace(
        id=13,
        status=ArchiveJobStatus.RUNNING,
        current_batch=0,
        processed_rows=0,
        batch_size=2,
        source_db="source",
        source_table="orders",
        dest_db="archive",
        dest_table="orders_archive",
        condition='{"status": "expired"}',
        sleep_ms=0,
    )
    docs = [{"_id": "a", "status": "expired"}, {"_id": "b", "status": "expired"}]

    class _FindResult:
        def limit(self, count):
            assert count == 2
            return self

        async def to_list(self, count):
            assert count == 2
            return docs

    src_collection = SimpleNamespace(
        find=MagicMock(return_value=_FindResult()),
        delete_many=AsyncMock(return_value=SimpleNamespace(deleted_count=1)),
    )
    dest_collection = SimpleNamespace(insert_many=AsyncMock())
    src_engine = SimpleNamespace(get_connection=AsyncMock(return_value={"source": {"orders": src_collection}}))
    dest_engine = SimpleNamespace(get_connection=AsyncMock(return_value={"archive": {"orders_archive": dest_collection}}))
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())

    with patch("app.services.archive.ArchiveService._log_batch", AsyncMock()) as log_batch, pytest.raises(AppException) as exc_info:
        await ArchiveService._execute_dest_mongo(db, job, src_engine, dest_engine)

    assert "目标已插入 2 行，但源表仅删除 1 行" in str(exc_info.value)
    assert job.status == ArchiveJobStatus.RUNNING
    assert job.current_batch == 0
    assert job.processed_rows == 0
    dest_collection.insert_many.assert_awaited_once_with(docs)
    src_collection.delete_many.assert_awaited_once_with({"_id": {"$in": ["a", "b"]}})
    log_batch.assert_awaited_once()
    _, logged_job, batch_no, status, selected_rows, inserted_rows, deleted_rows, message, _ = log_batch.await_args.args
    assert logged_job is job
    assert batch_no == 1
    assert status == ArchiveBatchStatus.FAILED
    assert selected_rows == 2
    assert inserted_rows == 2
    assert deleted_rows == 1
    assert "需人工核对" in message
    db.commit.assert_not_called()


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
