"""观测中心采集引擎域服务：指标采集调度、单实例采集、载荷归一与快照清理。

从 `MonitorService` 拆出的叶子模块（配合 `monitor_alerts.py` / `monitor_capacity.py`
的门面委托范式，见评估 #7）。采集为后台调度或已鉴权入口触发，本模块不做实例访问
鉴权（由 `MonitorService` 门面在入口完成），故不反向依赖门面；仅横向依赖告警 / 容量
两个兄弟叶子（无循环导入）。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instance import Instance
from app.models.monitor import (
    MonitorCollectConfig,
    MonitorDatabaseCapacitySnapshot,
    MonitorMetricSnapshot,
    MonitorTableCapacitySnapshot,
)
from app.services.monitor_alerts import MonitorAlertService
from app.services.monitor_capacity import MonitorCapacityService


class MonitorCollectService:
    """采集引擎域：到期实例批量采集、单实例指标采集、原始载荷归一与快照保留清理。"""

    @staticmethod
    async def collect_due_native(db: AsyncSession, limit: int | None = None) -> dict:
        now = datetime.now(UTC)
        cfg_rows = (
            await db.execute(
                select(MonitorCollectConfig, Instance)
                .join(Instance, MonitorCollectConfig.instance_id == Instance.id)
                .where(MonitorCollectConfig.is_enabled.is_(True), Instance.is_active.is_(True))
                .order_by(MonitorCollectConfig.id)
                .limit(limit or 1000)
            )
        ).all()
        collected = 0
        failed = 0
        skipped = 0
        capacity_collected = 0
        for cfg, inst in cfg_rows:
            metric_due = (
                not cfg.last_metric_collect_at
                or now - cfg.last_metric_collect_at >= timedelta(seconds=cfg.collect_interval)
            )
            capacity_due = (
                not cfg.last_capacity_collect_at
                or now - cfg.last_capacity_collect_at
                >= timedelta(seconds=cfg.capacity_collect_interval)
            )
            if not metric_due and not capacity_due:
                skipped += 1
                continue
            try:
                if metric_due:
                    await MonitorCollectService.collect_instance_metrics(
                        db, inst, cfg, collected_at=now
                    )
                    collected += 1
                if capacity_due:
                    await MonitorCapacityService.collect_instance_capacity(
                        db, inst, cfg, collected_at=now
                    )
                    capacity_collected += 1
                cfg.last_collect_status = "success"
                cfg.last_collect_error = ""
            except Exception as exc:
                failed += 1
                cfg.last_collect_status = "failed"
                cfg.last_collect_error = str(exc)[:4000]
                db.add(
                    MonitorMetricSnapshot(
                        instance_id=inst.id,
                        collected_at=now,
                        status="failed",
                        error=str(exc)[:4000],
                        is_up=False,
                    )
                )
            await MonitorCollectService.cleanup_old_snapshots(
                db, inst.id, cfg.retention_days, now
            )
        await db.commit()
        return {
            "instances": len(cfg_rows),
            "metric_collected": collected,
            "capacity_collected": capacity_collected,
            "failed": failed,
            "skipped": skipped,
        }

    @staticmethod
    async def collect_instance_metrics(
        db: AsyncSession,
        inst: Instance,
        cfg: MonitorCollectConfig,
        collected_at: datetime | None = None,
    ) -> MonitorMetricSnapshot:
        from app.engines.registry import get_engine

        now = collected_at or datetime.now(UTC)
        engine = get_engine(inst)
        previous = (
            await db.execute(
                select(MonitorMetricSnapshot)
                .where(MonitorMetricSnapshot.instance_id == inst.id)
                .order_by(MonitorMetricSnapshot.collected_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        raw = await engine.collect_metrics()
        normalized = MonitorCollectService._normalize_metric_payload(raw)
        MonitorCollectService._apply_delta_rates(normalized, raw, previous, now)
        snapshot = MonitorMetricSnapshot(instance_id=inst.id, collected_at=now, **normalized)
        db.add(snapshot)
        await db.flush()
        await MonitorAlertService.sync_alert_events_for_snapshot(db, inst, cfg, snapshot)
        cfg.last_metric_collect_at = now
        return snapshot

    @staticmethod
    async def cleanup_old_snapshots(
        db: AsyncSession, instance_id: int, retention_days: int, now: datetime | None = None
    ) -> None:
        cutoff = (now or datetime.now(UTC)) - timedelta(days=max(1, retention_days))
        for model in (
            MonitorMetricSnapshot,
            MonitorDatabaseCapacitySnapshot,
            MonitorTableCapacitySnapshot,
        ):
            rows = await db.execute(
                select(model).where(model.instance_id == instance_id, model.collected_at < cutoff)
            )
            for row in rows.scalars().all():
                await db.delete(row)

    @staticmethod
    def _normalize_metric_payload(raw: dict[str, Any]) -> dict[str, Any]:
        health = raw.get("health") or {}
        connections = raw.get("connections") or raw.get("stats") or {}
        stats = raw.get("stats") or raw.get("opcounters") or raw.get("metrics") or {}
        version = raw.get("version")
        if isinstance(version, dict):
            version = version.get("value") or version.get("version") or ""
        missing: dict[str, str] = {}
        if isinstance(raw.get("missing_groups"), dict):
            missing.update({str(k): str(v) for k, v in raw["missing_groups"].items()})
        if raw.get("error"):
            missing["health"] = "collect_failed"
        current_connections = MonitorCollectService._first_number(
            connections,
            "current",
            "connected_clients",
            "Threads_connected",
            "threads_connected",
            "current_connections",
        )
        max_connections = MonitorCollectService._first_number(
            raw.get("variables") or raw,
            "max_connections",
            "Max_used_connections",
        ) or MonitorCollectService._first_number(connections, "max_connections")
        usage = None
        if current_connections is not None and max_connections:
            usage = round(float(current_connections) / float(max_connections), 4)
        qps = MonitorCollectService._first_number(
            stats, "qps", "instantaneous_ops_per_sec", "queries_per_second"
        )
        tps = MonitorCollectService._first_number(stats, "tps", "transactions_per_second")
        return {
            "status": "failed" if raw.get("error") else "success",
            "error": str(raw.get("error") or ""),
            "missing_groups": missing,
            "is_up": bool(health.get("up")),
            "version": str(version or raw.get("server_version") or ""),
            "uptime_seconds": MonitorCollectService._first_number(raw, "uptime_seconds", "uptime")
            or MonitorCollectService._first_number(stats, "uptime_in_seconds"),
            "current_connections": current_connections,
            "active_sessions": MonitorCollectService._first_number(
                raw.get("queries") or connections, "active_sessions", "active", "current"
            ),
            "max_connections": max_connections,
            "connection_usage": usage,
            "qps": float(qps) if qps is not None else None,
            "tps": float(tps) if tps is not None else None,
            "slow_queries": MonitorCollectService._first_number(stats, "slow_queries", "Slow_queries"),
            "error_count": MonitorCollectService._first_number(stats, "errors", "error_count"),
            "lock_waits": MonitorCollectService._first_number(
                stats, "lock_waits", "Innodb_row_lock_waits"
            ),
            "long_transactions": MonitorCollectService._first_number(stats, "long_transactions"),
            "replication_lag_seconds": MonitorCollectService._first_number(
                raw.get("replication") or {}, "lag_seconds", "seconds_behind_master"
            ),
            "extra_metrics": MonitorCollectService._json_safe(raw),
        }

    @staticmethod
    def _apply_delta_rates(
        normalized: dict[str, Any],
        raw: dict[str, Any],
        previous: MonitorMetricSnapshot | None,
        now: datetime,
    ) -> None:
        """当引擎提供单调递增计数器时，优先使用区间速率。"""
        if not previous or not previous.collected_at:
            return
        previous_at = previous.collected_at
        if previous_at.tzinfo is None and now.tzinfo is not None:
            previous_at = previous_at.replace(tzinfo=UTC)
        seconds = max((now - previous_at).total_seconds(), 1)
        previous_extra = previous.extra_metrics or {}
        counters = raw.get("counters") or {}
        previous_counters = previous_extra.get("counters") or {}
        qps = MonitorCollectService._counter_rate(
            counters, previous_counters, seconds, "queries", "query_work"
        )
        tps = MonitorCollectService._counter_rate(
            counters, previous_counters, seconds, "transactions", "xact_total"
        )
        if qps is not None:
            normalized["qps"] = qps
        if tps is not None:
            normalized["tps"] = tps

    @staticmethod
    def _counter_rate(
        counters: dict[str, Any], previous_counters: dict[str, Any], seconds: float, *keys: str
    ) -> float | None:
        if not isinstance(counters, dict) or not isinstance(previous_counters, dict):
            return None
        for key in keys:
            current = MonitorCollectService._coerce_float(counters.get(key))
            previous = MonitorCollectService._coerce_float(previous_counters.get(key))
            if current is None or previous is None or current < previous:
                continue
            return round((current - previous) / seconds, 2)
        return None

    @staticmethod
    def _first_number(mapping: Any, *keys: str) -> int | float | None:
        if not isinstance(mapping, dict):
            return None
        lowered = {str(k).lower(): v for k, v in mapping.items()}
        for key in keys:
            value = lowered.get(key.lower())
            if value is None:
                continue
            try:
                return float(value) if "." in str(value) else int(value)
            except (TypeError, ValueError):
                continue
        return None

    # --- 本地工具（trivial pure；与 monitor_alerts / monitor_capacity 叶子的既有约定一致）---

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k): MonitorCollectService._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [MonitorCollectService._json_safe(v) for v in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return int(value) if value == value.to_integral_value() else float(value)
        return value
