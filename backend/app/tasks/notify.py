"""通知 Celery 任务。"""
from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import Callable
from typing import Any, TypeVar, cast

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

_TaskFunc = TypeVar("_TaskFunc", bound=Callable[..., Any])


def _typed_task(**kwargs: Any) -> Callable[[_TaskFunc], _TaskFunc]:
    return cast(Callable[[_TaskFunc], _TaskFunc], celery_app.task(**kwargs))


@_typed_task(
    bind=True,
    name="send_notification_event",
    queue="notify",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=3,
)
def send_notification_event_task(self: Any, payload: dict[str, Any]) -> None:
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


async def _send_notification_async(payload: dict[str, Any]) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import settings
    from app.services.notify import NotifyService

    importlib.import_module("app.models")
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async_session_local = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session_local() as db:
            await NotifyService.send_event(db, payload)
    finally:
        await engine.dispose()
