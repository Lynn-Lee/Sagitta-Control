"""通知 Celery 任务。"""
from __future__ import annotations

import asyncio
import importlib
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="send_notification_event", max_retries=0, queue="notify")
def send_notification_event_task(self, payload: dict):
    logger.info(
        "send_notification_event start: event=%s subject=%s:%s",
        payload.get("event_type"),
        payload.get("subject_type"),
        payload.get("subject_id"),
    )
    try:
        asyncio.run(_send_notification_async(payload))
    except Exception as exc:
        logger.error("send_notification_event failed: error=%s", str(exc))
        raise


async def _send_notification_async(payload: dict) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings
    from app.services.notify import NotifyService

    importlib.import_module("app.models")
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async_session_local = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session_local() as db:
            await NotifyService.send_event(db, payload)
    finally:
        await engine.dispose()
