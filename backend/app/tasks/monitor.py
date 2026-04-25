"""Monitor and session sampling tasks."""

import asyncio
import importlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app
from app.core.config import settings
from app.engines.models import ResultSet
from app.engines.registry import get_engine
from app.models.instance import Instance
from app.models.slowlog import SlowQueryConfig
from app.services.session_diagnostic import (
    DEFAULT_SESSION_RETENTION_DAYS,
    SessionDiagnosticService,
    is_collect_due,
)
from app.services.slowlog import DEFAULT_SLOW_THRESHOLD_MS, SlowLogService

logger = logging.getLogger(__name__)


async def _run_with_task_session(collector: Any, *args: Any, **kwargs: Any) -> dict:
    """Run a monitor collector with a Celery-local async engine.

    Celery tasks call ``asyncio.run`` for each invocation, so sharing the FastAPI
    global async engine can leave asyncpg connections attached to an old loop.
    """
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
            return await collector(db, *args, **kwargs)
    finally:
        await engine.dispose()


@celery_app.task(bind=True, queue="default")
def placeholder_task(self, *args, **kwargs):
    return {"task": "monitor", "status": "Sprint 实现中"}


async def _collect_session_snapshots_with_db(
    db: AsyncSession,
    retention_days: int = DEFAULT_SESSION_RETENTION_DAYS,
) -> dict:
    instances = (
        await db.execute(select(Instance).where(Instance.is_active.is_(True)))
    ).scalars().all()
    saved = 0
    failed = 0
    skipped = 0
    deleted = 0
    now = datetime.now(UTC)

    for inst in instances:
        cfg = await SessionDiagnosticService.ensure_default_config(db, inst)
        try:
            if not cfg.is_enabled:
                cfg.last_collect_status = "skipped"
                cfg.last_collect_error = "采集已禁用"
                cfg.last_collect_count = 0
                skipped += 1
                deleted += await SessionDiagnosticService.cleanup_old_snapshots(
                    db,
                    retention_days=cfg.retention_days,
                    instance_id=inst.id,
                )
                continue
            if not is_collect_due(cfg, now):
                skipped += 1
                deleted += await SessionDiagnosticService.cleanup_old_snapshots(
                    db,
                    retention_days=cfg.retention_days,
                    instance_id=inst.id,
                )
                continue
            engine = get_engine(inst)
            rs = await engine.processlist(command_type="ALL")
            count = await SessionDiagnosticService.save_snapshot(db, inst, rs, collected_at=now)
            if rs.error:
                cfg.last_collect_status = "failed"
                cfg.last_collect_error = rs.error[:2000]
                cfg.last_collect_count = 0
                failed += 1
            else:
                cfg.last_collect_status = "success"
                cfg.last_collect_error = ""
                cfg.last_collect_count = count
                saved += count
            cfg.last_collect_at = now
        except Exception as exc:
            logger.warning(
                "session_snapshot_collect_failed instance_id=%s error=%s",
                inst.id,
                exc,
            )
            failed += 1
            cfg.last_collect_status = "failed"
            cfg.last_collect_error = str(exc)[:2000]
            cfg.last_collect_count = 0
            cfg.last_collect_at = now
            await SessionDiagnosticService.save_snapshot(db, inst, ResultSet(error=str(exc)), collected_at=now)

        deleted += await SessionDiagnosticService.cleanup_old_snapshots(
            db,
            retention_days=cfg.retention_days,
            instance_id=inst.id,
        )

    await db.commit()
    return {
        "instances": len(instances),
        "saved": saved,
        "failed": failed,
        "skipped": skipped,
        "deleted": deleted,
        "retention_days": retention_days,
    }


async def _collect_session_snapshots_async(retention_days: int = DEFAULT_SESSION_RETENTION_DAYS) -> dict:
    return await _run_with_task_session(
        _collect_session_snapshots_with_db,
        retention_days=retention_days,
    )


@celery_app.task(name="collect_session_snapshots", queue="monitor")
def collect_session_snapshots(retention_days: int = 30) -> dict:
    return asyncio.run(_collect_session_snapshots_async(retention_days=retention_days))


async def _collect_slow_queries_with_db(db: AsyncSession, retention_days: int = 30, limit: int = 100) -> dict:
    instances = (
        await db.execute(select(Instance).where(Instance.is_active.is_(True)))
    ).scalars().all()
    saved = await SlowLogService.sync_platform_logs(db, threshold_ms=DEFAULT_SLOW_THRESHOLD_MS)
    failed = 0
    unsupported = 0
    skipped = 0
    now = datetime.now(UTC)

    for inst in instances:
        try:
            cfg = await SlowLogService.ensure_default_config(db, inst)
            if not cfg.is_enabled:
                skipped += 1
                continue
            if cfg.last_collect_at and now - cfg.last_collect_at < timedelta(seconds=cfg.collect_interval):
                skipped += 1
                continue
            count, err = await SlowLogService.collect_instance(
                db,
                inst,
                limit=min(limit, cfg.collect_limit),
                config=cfg,
            )
            saved += count
            if err:
                if "暂不支持" in err:
                    unsupported += 1
                else:
                    failed += 1
        except Exception as exc:
            logger.warning(
                "slow_query_collect_failed instance_id=%s error=%s",
                inst.id,
                exc,
            )
            failed += 1

    cfg_days = (
        await db.execute(select(SlowQueryConfig.retention_days).where(SlowQueryConfig.is_enabled.is_(True)))
    ).scalars().all()
    effective_retention_days = min(cfg_days) if cfg_days else retention_days
    deleted = await SlowLogService.cleanup_old_logs(db, effective_retention_days)
    await db.commit()
    return {
        "instances": len(instances),
        "saved": saved,
        "failed": failed,
        "unsupported": unsupported,
        "skipped": skipped,
        "deleted": deleted,
        "retention_days": effective_retention_days,
    }


async def _collect_slow_queries_async(retention_days: int = 30, limit: int = 100) -> dict:
    return await _run_with_task_session(
        _collect_slow_queries_with_db,
        retention_days=retention_days,
        limit=limit,
    )


@celery_app.task(name="collect_slow_queries", queue="monitor")
def collect_slow_queries(retention_days: int = 30, limit: int = 100) -> dict:
    return asyncio.run(_collect_slow_queries_async(retention_days=retention_days, limit=limit))
