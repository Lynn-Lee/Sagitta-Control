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

archive_task_module = importlib.import_module("app.tasks.archive")


class _AsyncSessionContext:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _session_factory(db):
    return lambda: _AsyncSessionContext(db)


@pytest.mark.asyncio
async def test_execute_archive_async_disposes_engine_when_service_raises():
    db = AsyncMock()
    engine = SimpleNamespace(dispose=AsyncMock())

    with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=engine), patch(
        "sqlalchemy.ext.asyncio.async_sessionmaker", return_value=_session_factory(db)
    ), patch(
        "app.services.archive.ArchiveService.execute_job",
        AsyncMock(side_effect=RuntimeError("archive failed")),
    ), pytest.raises(RuntimeError, match="archive failed"):
        await archive_task_module._execute_archive_async(11, 2)

    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_scheduled_archive_async_disposes_engine_when_service_raises():
    db = AsyncMock()
    engine = SimpleNamespace(dispose=AsyncMock())

    with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=engine), patch(
        "sqlalchemy.ext.asyncio.async_sessionmaker", return_value=_session_factory(db)
    ), patch(
        "app.services.archive.ArchiveService.dispatch_scheduled_jobs",
        AsyncMock(side_effect=RuntimeError("dispatch failed")),
    ), pytest.raises(RuntimeError, match="dispatch failed"):
        await archive_task_module._dispatch_scheduled_archive_async()

    engine.dispose.assert_awaited_once()
