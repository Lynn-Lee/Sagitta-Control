import importlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeConf:
    def update(self, *args, **kwargs):
        return None


class _FakeCelery:
    def __init__(self, *args, **kwargs):
        self.conf = _FakeConf()

    def task(self, *args, **kwargs):
        return lambda fn: fn


sys.modules.setdefault(
    "celery",
    SimpleNamespace(Celery=_FakeCelery),
)
sys.modules.setdefault(
    "celery.schedules",
    SimpleNamespace(crontab=lambda *args, **kwargs: ("crontab", args, kwargs)),
)

WorkflowStatus = importlib.import_module("app.models.workflow").WorkflowStatus
execute_sql_task_module = importlib.import_module("app.tasks.execute_sql")


class _AsyncSessionContext:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _session_factory(db):
    return lambda: _AsyncSessionContext(db)


class TestExecuteWorkflowTask:
    def test_execute_workflow_task_runs_async_executor(self):
        with patch.object(execute_sql_task_module.asyncio, "run") as run_mock, patch.object(
            execute_sql_task_module, "_execute_async", MagicMock(return_value="coroutine")
        ):
            execute_sql_task_module.execute_workflow_task(None, 12, 34)

        run_mock.assert_called_once_with("coroutine")

    def test_execute_workflow_task_bubbles_up_failures(self):
        with patch.object(
            execute_sql_task_module.asyncio,
            "run",
            side_effect=RuntimeError("boom"),
        ), patch.object(
            execute_sql_task_module,
            "_execute_async",
            MagicMock(return_value="coroutine"),
        ), pytest.raises(RuntimeError, match="boom"):
            execute_sql_task_module.execute_workflow_task(None, 12, 34)


class TestExecuteAsync:
    @pytest.mark.asyncio
    async def test_execute_async_returns_when_workflow_missing(self):
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=MagicMock(return_value=None))
        )
        engine = SimpleNamespace(dispose=AsyncMock())

        with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=engine), patch(
            "sqlalchemy.orm.sessionmaker", return_value=_session_factory(db)
        ):
            await execute_sql_task_module._execute_async(1, 2)

        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_async_marks_exception_when_instance_missing(self):
        workflow = SimpleNamespace(
            id=3,
            instance_id=8,
            db_name="testdb",
            content=SimpleNamespace(sql_content="select 1", execute_result=None),
            status=WorkflowStatus.QUEUING,
            execute_mode=None,
            executed_by_id=None,
            executed_by_name=None,
            finish_time=None,
        )
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=MagicMock(return_value=workflow)),
                SimpleNamespace(scalar_one_or_none=MagicMock(return_value=SimpleNamespace(username="operator"))),
                SimpleNamespace(scalar_one_or_none=MagicMock(return_value=None)),
            ]
        )
        engine = SimpleNamespace(dispose=AsyncMock())

        with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=engine), patch(
            "sqlalchemy.orm.sessionmaker", return_value=_session_factory(db)
        ):
            await execute_sql_task_module._execute_async(3, 2)

        assert workflow.status == WorkflowStatus.EXCEPTION
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_async_finishes_workflow_and_writes_log(self):
        workflow = SimpleNamespace(
            id=5,
            instance_id=9,
            db_name="analytics",
            content=SimpleNamespace(sql_content="select 1", execute_result=None),
            status=WorkflowStatus.QUEUING,
            execute_mode=None,
            executed_by_id=None,
            executed_by_name=None,
            finish_time=None,
        )
        operator_user = SimpleNamespace(username="dba_user")
        instance = SimpleNamespace(id=9)
        audit = SimpleNamespace(id=101)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=MagicMock(return_value=workflow)),
                SimpleNamespace(scalar_one_or_none=MagicMock(return_value=operator_user)),
                SimpleNamespace(scalar_one_or_none=MagicMock(return_value=instance)),
                SimpleNamespace(scalar_one_or_none=MagicMock(return_value=audit)),
            ]
        )
        engine = SimpleNamespace(dispose=AsyncMock())
        db_engine = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(error="")))

        with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=engine), patch(
            "sqlalchemy.orm.sessionmaker", return_value=_session_factory(db)
        ), patch("app.engines.registry.get_engine", return_value=db_engine), patch(
            "app.services.audit.AuditService._write_log", AsyncMock()
        ) as write_log_mock:
            await execute_sql_task_module._execute_async(5, 7)

        assert workflow.status == WorkflowStatus.FINISH
        assert workflow.content.execute_result == '{"success": true, "error": ""}'
        assert workflow.finish_time is not None
        assert db.commit.await_count == 2
        db_engine.execute.assert_awaited_once_with(db_name="analytics", sql="select 1")
        write_log_mock.assert_awaited_once()
        engine.dispose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_async_records_engine_errors(self):
        workflow = SimpleNamespace(
            id=6,
            instance_id=9,
            db_name="analytics",
            content=SimpleNamespace(sql_content="delete from orders", execute_result=None),
            status=WorkflowStatus.QUEUING,
            execute_mode=None,
            executed_by_id=None,
            executed_by_name=None,
            finish_time=None,
        )
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=MagicMock(return_value=workflow)),
                SimpleNamespace(scalar_one_or_none=MagicMock(return_value=SimpleNamespace(username="auditor"))),
                SimpleNamespace(scalar_one_or_none=MagicMock(return_value=SimpleNamespace(id=9))),
                SimpleNamespace(scalar_one_or_none=MagicMock(return_value=None)),
            ]
        )
        engine = SimpleNamespace(dispose=AsyncMock())
        db_engine = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("sql failed")))

        with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=engine), patch(
            "sqlalchemy.orm.sessionmaker", return_value=_session_factory(db)
        ), patch("app.engines.registry.get_engine", return_value=db_engine):
            await execute_sql_task_module._execute_async(6, 7)

        assert workflow.status == WorkflowStatus.EXCEPTION
        assert workflow.content.execute_result == '{"error": "sql failed"}'
        assert workflow.finish_time is not None
        assert db.commit.await_count == 2
        engine.dispose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_async_skips_non_executable_status(self):
        workflow = SimpleNamespace(id=7, status=WorkflowStatus.REVIEW_PASS)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=MagicMock(return_value=workflow)))
        engine = SimpleNamespace(dispose=AsyncMock())

        with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=engine), patch(
            "sqlalchemy.orm.sessionmaker", return_value=_session_factory(db)
        ):
            await execute_sql_task_module._execute_async(7, 2)

        db.commit.assert_not_awaited()
        engine.dispose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatch_scheduled_async_enqueues_due_workflows(self):
        workflow = SimpleNamespace(
            id=8,
            engineer_id=3,
            executed_by_id=9,
            status=WorkflowStatus.TIMING_TASK,
            execute_mode="scheduled",
        )
        result = MagicMock()
        result.scalars.return_value.all.return_value = [workflow]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)
        engine = SimpleNamespace(dispose=AsyncMock())

        with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=engine), patch(
            "sqlalchemy.orm.sessionmaker", return_value=_session_factory(db)
        ), patch.object(execute_sql_task_module.execute_workflow_task, "delay", create=True) as delay_mock:
            dispatched = await execute_sql_task_module._dispatch_scheduled_async()

        assert dispatched == 1
        assert workflow.status == WorkflowStatus.QUEUING
        delay_mock.assert_called_once_with(8, 9)
        db.commit.assert_awaited_once()
        engine.dispose.assert_awaited_once()
