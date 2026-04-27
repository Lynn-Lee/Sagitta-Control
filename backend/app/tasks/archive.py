"""Archive Celery tasks."""
from __future__ import annotations

import asyncio
import importlib
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="execute_archive_job", max_retries=0, queue="archive")
def execute_archive_job_task(self, job_id: int, operator_id: int):
    logger.info("execute_archive_job start: job_id=%s", job_id)
    try:
        asyncio.run(_execute_archive_async(job_id, operator_id))
    except Exception as exc:
        logger.error("execute_archive_job failed: job_id=%s error=%s", job_id, str(exc))
        raise
    logger.info("execute_archive_job done: job_id=%s", job_id)


@celery_app.task(bind=True, name="dispatch_scheduled_archive_jobs", max_retries=0, queue="archive")
def dispatch_scheduled_archive_jobs_task(self):
    logger.info("dispatch_scheduled_archive_jobs start")
    try:
        dispatched = asyncio.run(_dispatch_scheduled_archive_async())
        logger.info("dispatch_scheduled_archive_jobs done: dispatched=%s", dispatched)
        return dispatched
    except Exception as exc:
        logger.error("dispatch_scheduled_archive_jobs failed: error=%s", str(exc))
        raise


async def _execute_archive_async(job_id: int, operator_id: int) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings
    from app.services.archive import ArchiveService

    importlib.import_module("app.models")
    engine = create_async_engine(settings.DATABASE_URL)
    async_session_local = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_local() as db:
        await ArchiveService.execute_job(db, job_id, operator_id)
    await engine.dispose()


async def _dispatch_scheduled_archive_async() -> int:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings
    from app.services.archive import ArchiveService

    importlib.import_module("app.models")
    engine = create_async_engine(settings.DATABASE_URL)
    async_session_local = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_local() as db:
        dispatched = await ArchiveService.dispatch_scheduled_jobs(db)
    await engine.dispose()
    return dispatched
