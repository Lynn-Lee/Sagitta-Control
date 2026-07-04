"""监控与会话采样任务。"""

from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.core.config import settings
from app.engines.models import ResultSet
from app.engines.registry import get_engine
from app.models.instance import Instance
from app.models.slowlog import SlowQueryConfig
from app.services.monitor import MonitorService
from app.services.session_diagnostic import (
    DEFAULT_SESSION_RETENTION_DAYS,
    SessionDiagnosticService,
    is_collect_due,
)
from app.services.slowlog import SlowLogService

logger = logging.getLogger(__name__)

_TaskFunc = TypeVar("_TaskFunc", bound=Callable[..., Any])


def _typed_task(**kwargs: Any) -> Callable[[_TaskFunc], _TaskFunc]:
    return cast(Callable[[_TaskFunc], _TaskFunc], celery_app.task(**kwargs))


async def _run_with_task_session(
    collector: Callable[..., Awaitable[dict[str, Any]]],
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """使用 Celery 进程内的本地 async engine 运行监控采集器。

    Celery 任务每次执行都会调用 ``asyncio.run``，如果复用 FastAPI 全局 async engine，
    asyncpg 连接可能仍绑定在旧事件循环上。
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
    async_session_local = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with async_session_local() as db:
            return await collector(db, *args, **kwargs)
    finally:
        await engine.dispose()


async def _collect_session_snapshots_with_db(
    db: AsyncSession,
    retention_days: int = DEFAULT_SESSION_RETENTION_DAYS,
) -> dict[str, Any]:
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
            processlist = getattr(engine, "processlist", None)
            if not callable(processlist):
                cfg.last_collect_status = "skipped"
                cfg.last_collect_error = f"{inst.db_type} 暂不支持会话采集"
                cfg.last_collect_count = 0
                cfg.last_collect_at = now
                skipped += 1
                deleted += await SessionDiagnosticService.cleanup_old_snapshots(
                    db,
                    retention_days=cfg.retention_days,
                    instance_id=inst.id,
                )
                continue
            rs = await processlist(command_type="ALL")
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


async def _collect_session_snapshots_async(
    retention_days: int = DEFAULT_SESSION_RETENTION_DAYS,
) -> dict[str, Any]:
    return await _run_with_task_session(
        _collect_session_snapshots_with_db,
        retention_days=retention_days,
    )


@_typed_task(
    name="collect_session_snapshots",
    queue="monitor",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=2,
)
def collect_session_snapshots(retention_days: int = 30) -> dict[str, Any]:
    return asyncio.run(_collect_session_snapshots_async(retention_days=retention_days))


async def _collect_slow_queries_with_db(
    db: AsyncSession,
    retention_days: int = 30,
    limit: int = 100,
) -> dict[str, Any]:
    instances = (
        await db.execute(select(Instance).where(Instance.is_active.is_(True)))
    ).scalars().all()
    saved = 0
    failed = 0
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
        "unsupported": 0,
        "skipped": skipped,
        "deleted": deleted,
        "retention_days": effective_retention_days,
    }


async def _collect_slow_queries_async(
    retention_days: int = 30,
    limit: int = 100,
) -> dict[str, Any]:
    return await _run_with_task_session(
        _collect_slow_queries_with_db,
        retention_days=retention_days,
        limit=limit,
    )


@_typed_task(
    name="collect_slow_queries",
    queue="monitor",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=2,
)
def collect_slow_queries(retention_days: int = 30, limit: int = 100) -> dict[str, Any]:
    return asyncio.run(_collect_slow_queries_async(retention_days=retention_days, limit=limit))


async def _collect_native_monitoring_with_db(
    db: AsyncSession,
    limit: int | None = None,
) -> dict[str, Any]:
    return await MonitorService.collect_due_native(db, limit=limit)


async def _collect_native_monitoring_async(limit: int | None = None) -> dict[str, Any]:
    return await _run_with_task_session(_collect_native_monitoring_with_db, limit=limit)


@_typed_task(
    name="collect_native_monitoring",
    queue="monitor",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=2,
)
def collect_native_monitoring(limit: int | None = None) -> dict[str, Any]:
    return asyncio.run(_collect_native_monitoring_async(limit=limit))
