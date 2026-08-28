import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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


sys.modules.setdefault("celery", SimpleNamespace(Celery=_FakeCelery))
sys.modules.setdefault("celery.schedules", SimpleNamespace(crontab=lambda *args, **kwargs: ("crontab", args, kwargs)))

from app.tasks import license as license_task  # noqa: E402


@pytest.mark.asyncio
async def test_refresh_online_license_notifies_renewal_window(monkeypatch):
    events: list[dict] = []

    async def fake_status(_db):
        return {
            "status": "licensed",
            "source": "online",
            "license_id": "lic-001",
            "company_name": "Acme Corp",
            "days_remaining": 7,
        }

    async def fake_refresh(_db):
        return {
            "status": "licensed",
            "source": "online",
            "license_id": "lic-001",
            "company_name": "Acme Corp",
            "days_remaining": 7,
        }

    monkeypatch.setattr(license_task.settings, "LICENSE_AUTO_REFRESH_ENABLED", True)
    monkeypatch.setattr(license_task.settings, "LICENSE_RENEWAL_NOTIFY_DAYS", "30,7")
    monkeypatch.setattr(license_task.LicenseService, "status", fake_status)
    monkeypatch.setattr(license_task.LicenseService, "refresh", fake_refresh)
    monkeypatch.setattr(
        license_task.LicenseService,
        "sync_instance_suspension",
        AsyncMock(return_value={"suspended": 0, "restored": 0}),
    )
    monkeypatch.setattr(license_task.NotifyService, "enqueue_event", events.append)

    result = await license_task._refresh_online_license_with_db(MagicMock())

    assert result["refreshed"] is True
    assert result["days_remaining"] == 7
    assert events[0]["event_type"] == "license_renewal_warning"
    assert events[0]["permissions"] == ["system_config_manage"]


@pytest.mark.asyncio
async def test_refresh_online_license_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(license_task.settings, "LICENSE_AUTO_REFRESH_ENABLED", False)
    monkeypatch.setattr(
        license_task.LicenseService,
        "status",
        AsyncMock(return_value={"status": "licensed", "source": "online"}),
    )
    refresh = AsyncMock()
    monkeypatch.setattr(license_task.LicenseService, "refresh", refresh)

    result = await license_task._refresh_online_license_with_db(MagicMock())

    assert result["skipped"] == "disabled"
    refresh.assert_not_awaited()
