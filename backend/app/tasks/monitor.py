"""Monitor and session sampling tasks."""

import asyncio
import logging

from sqlalchemy import select

from app.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.engines.models import ResultSet
from app.engines.registry import get_engine
from app.models.instance import Instance
from app.models.slowlog import SlowQueryConfig
from app.services.session_diagnostic import SessionDiagnosticService
from app.services.slowlog import DEFAULT_SLOW_THRESHOLD_MS, SlowLogService

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, queue="default")
def placeholder_task(self, *args, **kwargs):
    return {"task": "monitor", "status": "Sprint 实现中"}


async def _collect_session_snapshots_async(retention_days: int = 30) -> dict:
    async with AsyncSessionLocal() as db:
        instances = (
            await db.execute(select(Instance).where(Instance.is_active.is_(True)))
        ).scalars().all()
        saved = 0
        failed = 0

        for inst in instances:
            try:
                engine = get_engine(inst)
                rs = await engine.processlist(command_type="ALL")
                saved += await SessionDiagnosticService.save_snapshot(db, inst, rs)
                if rs.error:
                    failed += 1
            except Exception as exc:
                logger.warning(
                    "session_snapshot_collect_failed instance_id=%s error=%s",
                    inst.id,
                    exc,
                )
                failed += 1
                saved += await SessionDiagnosticService.save_snapshot(
                    db, inst, ResultSet(error=str(exc))
                )

        deleted = await SessionDiagnosticService.cleanup_old_snapshots(db, retention_days)
        await db.commit()
        return {
            "instances": len(instances),
            "saved": saved,
            "failed": failed,
            "deleted": deleted,
            "retention_days": retention_days,
        }


@celery_app.task(name="collect_session_snapshots", queue="monitor")
def collect_session_snapshots(retention_days: int = 30) -> dict:
    return asyncio.run(_collect_session_snapshots_async(retention_days=retention_days))


async def _collect_slow_queries_async(retention_days: int = 30, limit: int = 100) -> dict:
    async with AsyncSessionLocal() as db:
        instances = (
            await db.execute(select(Instance).where(Instance.is_active.is_(True)))
        ).scalars().all()
        saved = await SlowLogService.sync_platform_logs(db, threshold_ms=DEFAULT_SLOW_THRESHOLD_MS)
        failed = 0
        unsupported = 0
        skipped = 0
        from datetime import UTC, datetime, timedelta

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


@celery_app.task(name="collect_slow_queries", queue="monitor")
def collect_slow_queries(retention_days: int = 30, limit: int = 100) -> dict:
    return asyncio.run(_collect_slow_queries_async(retention_days=retention_days, limit=limit))
