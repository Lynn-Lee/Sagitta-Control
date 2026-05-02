"""License 维护任务。"""

from __future__ import annotations

import asyncio
import importlib
import logging

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app
from app.core.config import settings
from app.services.license import LicenseService
from app.services.notify import NotifyService

logger = logging.getLogger(__name__)


async def _run_with_session(handler):
    importlib.import_module("app.models")
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_pre_ping=True,
        echo=settings.DEBUG,
    )
    async_session_local = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with async_session_local() as db:
            return await handler(db)
    finally:
        await engine.dispose()


def _renewal_days() -> set[int]:
    result: set[int] = set()
    for item in settings.LICENSE_RENEWAL_NOTIFY_DAYS.split(","):
        try:
            value = int(item.strip())
        except ValueError:
            continue
        if value >= 0:
            result.add(value)
    return result


async def _refresh_online_license_with_db(db: AsyncSession) -> dict:
    state = await LicenseService.status(db)
    if not settings.LICENSE_AUTO_REFRESH_ENABLED:
        return {"status": state["status"], "skipped": "disabled"}

    refreshed = False
    error = ""
    if state.get("source") == "online":
        try:
            state = await LicenseService.refresh(db)
            refreshed = True
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            logger.warning("license_auto_refresh_failed: %s", error)

    days_remaining = state.get("days_remaining")
    if isinstance(days_remaining, int) and days_remaining in _renewal_days():
        NotifyService.enqueue_event(
            {
                "event_type": "license_renewal_warning",
                "subject_type": "license",
                "subject_id": 0,
                "app_type": "商业授权",
                "title": state.get("company_name") or state.get("license_id") or "SagittaDB License",
                "applicant_name": "系统",
                "permissions": ["system_config_manage"],
                "remark": f"License 将在 {days_remaining} 天后到期，请及时续期或刷新授权。",
                "detail_path": "/system/license",
            }
        )

    return {
        "status": state.get("status"),
        "license_id": state.get("license_id"),
        "source": state.get("source"),
        "refreshed": refreshed,
        "error": error,
        "days_remaining": days_remaining,
    }


@celery_app.task(bind=True, name="refresh_online_license", max_retries=0, queue="default")
def refresh_online_license_task(self):
    return asyncio.run(_run_with_session(_refresh_online_license_with_db))
