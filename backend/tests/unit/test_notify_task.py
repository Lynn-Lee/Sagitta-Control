import importlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


class _FakeConf:
    def update(self, *args, **kwargs):
        return None


class _FakeCelery:
    def __init__(self, *args, **kwargs):
        self.conf = _FakeConf()

    def task(self, *args, **kwargs):
        def decorator(fn):
            fn._celery_task_args = args
            fn._celery_task_kwargs = kwargs
            return fn

        return decorator


sys.modules.setdefault(
    "celery",
    SimpleNamespace(Celery=_FakeCelery),
)
sys.modules.setdefault(
    "celery.schedules",
    SimpleNamespace(crontab=lambda *args, **kwargs: ("crontab", args, kwargs)),
)

notify_task_module = importlib.import_module("app.tasks.notify")
monitor_task_module = importlib.import_module("app.tasks.monitor")


class _AsyncSessionContext:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _session_factory(db):
    return lambda: _AsyncSessionContext(db)


def _task_kwargs(task):
    fake_kwargs = getattr(task, "_celery_task_kwargs", None)
    if fake_kwargs is not None:
        return fake_kwargs
    return {
        "autoretry_for": task.autoretry_for,
        "retry_backoff": task.retry_backoff,
        "retry_backoff_max": task.retry_backoff_max,
        "max_retries": task.max_retries,
        "queue": task.queue,
    }


def test_send_notification_event_uses_bounded_autoretry_for_transient_failures():
    task_kwargs = _task_kwargs(notify_task_module.send_notification_event_task)

    assert task_kwargs["autoretry_for"] == (ConnectionError, TimeoutError)
    assert task_kwargs["retry_backoff"] is True
    assert task_kwargs["retry_backoff_max"] == 120
    assert task_kwargs["max_retries"] == 3
    assert task_kwargs["queue"] == "notify"


@pytest.mark.parametrize(
    "task",
    [
        monitor_task_module.collect_session_snapshots,
        monitor_task_module.collect_slow_queries,
        monitor_task_module.collect_native_monitoring,
    ],
)
def test_monitor_collection_tasks_use_bounded_autoretry_for_transient_failures(task):
    task_kwargs = _task_kwargs(task)

    assert task_kwargs["autoretry_for"] == (ConnectionError, TimeoutError, OSError)
    assert task_kwargs["retry_backoff"] is True
    assert task_kwargs["retry_backoff_max"] == 60
    assert task_kwargs["max_retries"] == 2
    assert task_kwargs["queue"] == "monitor"


@pytest.mark.asyncio
async def test_send_notification_async_disposes_engine_when_service_raises():
    db = AsyncMock()
    engine = SimpleNamespace(dispose=AsyncMock())

    with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=engine), patch(
        "sqlalchemy.orm.sessionmaker", return_value=_session_factory(db)
    ), patch(
        "app.services.notify.NotifyService.send_event",
        AsyncMock(side_effect=RuntimeError("notify failed")),
    ), pytest.raises(RuntimeError, match="notify failed"):
        await notify_task_module._send_notification_async({"event_type": "execution_failed"})

    engine.dispose.assert_awaited_once()
