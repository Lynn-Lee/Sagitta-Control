"""观测中心 + Dashboard 统计服务（Sprint 5）。"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, NotFoundException
from app.models.instance import Instance
from app.models.monitor import (
    MonitorAlertEvent,
    MonitorCollectConfig,
    MonitorMetricSnapshot,
    MonitorPrivilege,
    MonitorPrivilegeApply,
)
from app.models.user import ResourceGroup
from app.schemas.monitor import (
    MonitorConfigCreate,
    MonitorConfigUpdate,
    NativeMonitorConfigUpsert,
)
from app.services.dashboard import DashboardService
from app.services.monitor_alerts import MonitorAlertService
from app.services.monitor_capacity import MonitorCapacityService
from app.services.monitor_collect import MonitorCollectService
from app.services.monitor_config import MonitorConfigService

logger = logging.getLogger(__name__)

__all__ = ["DashboardService", "MonitorService"]


class MonitorService:
    ACTIVITY_TOP_SQL_TYPES = {
        "tidb",
        "starrocks",
        "doris",
        "oracle",
        "mssql",
        "sqlserver",
        "clickhouse",
        "elasticsearch",
        "opensearch",
    }
    RISK_LABELS = {
        "healthy": "健康",
        "attention": "关注",
        "warning": "警告",
        "critical": "严重",
    }
    METRIC_GROUP_META_KEYS = {
        "error",
        "health",
        "missing_groups",
        "metric_groups",
        "server_version",
        "version",
    }

    @staticmethod
    def _can_access_instance(user: dict[str, Any], instance: Instance) -> bool:
        # 观测域实例访问判定统一收敛到 MonitorAlertService，避免两处重复实现漂移
        return MonitorAlertService._can_access_instance(user, instance)

    @staticmethod
    async def list_configs(
        db: AsyncSession,
        user: dict[str, Any],
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[int, list[dict[str, Any]]]:
        return await MonitorConfigService.list_configs(db, user, page=page, page_size=page_size)

    @staticmethod
    async def create_config(
        db: AsyncSession, data: MonitorConfigCreate, operator: dict[str, Any]
    ) -> MonitorCollectConfig:
        return await MonitorConfigService.create_config(db, data, operator)

    @staticmethod
    async def update_config_with_access(
        db: AsyncSession,
        config_id: int,
        data: MonitorConfigUpdate,
        user: dict[str, Any],
    ) -> MonitorCollectConfig:
        return await MonitorConfigService.update_config_with_access(db, config_id, data, user)

    @staticmethod
    async def delete_config(db: AsyncSession, config_id: int, user: dict[str, Any]) -> None:
        await MonitorConfigService.delete_config(db, config_id, user)

    @staticmethod
    async def get_sd_targets(db: AsyncSession) -> list[dict[str, Any]]:
        return await MonitorConfigService.get_sd_targets(db)

    @staticmethod
    async def apply_privilege(db: AsyncSession, data: Any, user: dict[str, Any]) -> MonitorPrivilegeApply:
        return await MonitorConfigService.apply_privilege(db, data, user)

    @staticmethod
    async def audit_privilege(
        db: AsyncSession, apply_id: int, action: str, operator: dict[str, Any], remark: str = ""
    ) -> MonitorPrivilegeApply:
        return await MonitorConfigService.audit_privilege(db, apply_id, action, operator, remark)

    @staticmethod
    async def check_privilege(db: AsyncSession, user: dict[str, Any], instance_id: int) -> bool:
        return await MonitorConfigService.check_privilege(db, user, instance_id)

    @staticmethod
    async def list_applies(
        db: AsyncSession, user: dict[str, Any], status: int | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[int, list[MonitorPrivilegeApply]]:
        return await MonitorConfigService.list_applies(
            db, user, status=status, page=page, page_size=page_size
        )

    @staticmethod
    async def upsert_native_config(
        db: AsyncSession,
        instance_id: int,
        data: Any,
        user: dict[str, Any],
    ) -> MonitorCollectConfig:
        return await MonitorConfigService.upsert_native_config(db, instance_id, data, user)

    @staticmethod
    async def collect_native_now(db: AsyncSession, instance_id: int, user: dict[str, Any]) -> dict[str, Any]:
        """手动触发原生监控采集：确保采集配置存在，执行指标与容量采集并回写状态。

        get_native_detail 内部已做实例访问校验；采集失败时记录失败快照并抛出 400。
        """
        detail = await MonitorService.get_native_detail(db, instance_id, user)
        if not detail.get("config"):
            await MonitorService.upsert_native_config(
                db, instance_id, NativeMonitorConfigUpsert(), user
            )
        cfg = (
            await db.execute(
                select(MonitorCollectConfig).where(
                    MonitorCollectConfig.instance_id == instance_id
                )
            )
        ).scalar_one()
        inst = (
            await db.execute(select(Instance).where(Instance.id == instance_id))
        ).scalar_one()
        try:
            snapshot = await MonitorCollectService.collect_instance_metrics(db, inst, cfg)
            await MonitorCapacityService.collect_instance_capacity(db, inst, cfg)
            cfg.last_collect_status = "success"
            cfg.last_collect_error = ""
            await db.commit()
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            cfg.last_collect_status = "failed"
            cfg.last_collect_error = error[:4000]
            db.add(
                MonitorMetricSnapshot(
                    instance_id=inst.id,
                    collected_at=datetime.now(UTC),
                    status="failed",
                    error=error[:4000],
                    is_up=False,
                )
            )
            await db.commit()
            logger.warning(
                "native_monitor_manual_collect_failed: instance_id=%s error=%s",
                instance_id,
                error,
            )
            raise AppException(f"采集失败：{error}", code=400) from exc
        return MonitorService._snapshot_to_dict(snapshot)

    @staticmethod
    async def list_unified_collect_configs(db: AsyncSession, user: dict[str, Any]) -> dict[str, Any]:
        return await MonitorConfigService.list_unified_collect_configs(db, user)

    @staticmethod
    async def upsert_unified_collect_config(
        db: AsyncSession,
        instance_id: int,
        data: Any,
        user: dict[str, Any],
    ) -> dict[str, Any]:
        return await MonitorConfigService.upsert_unified_collect_config(db, instance_id, data, user)

    @staticmethod
    async def bulk_upsert_unified_collect_configs(
        db: AsyncSession,
        data: Any,
        user: dict[str, Any],
    ) -> dict[str, Any]:
        return await MonitorConfigService.bulk_upsert_unified_collect_configs(db, data, user)

    @staticmethod
    async def list_native_instances(db: AsyncSession, user: dict[str, Any]) -> list[dict[str, Any]]:
        stmt = (
            select(Instance)
            .options(selectinload(Instance.resource_groups))
            .where(Instance.is_active.is_(True))
        )
        if not (user.get("is_superuser") or "observability_instance_all" in user.get("permissions", [])):
            user_rg_ids = user.get("resource_groups", [])
            privileged_instance_ids = (
                (
                    await db.execute(
                        select(MonitorPrivilege.instance_id).where(
                            MonitorPrivilege.user_id == user.get("id"),
                            MonitorPrivilege.valid_date >= date.today(),
                            MonitorPrivilege.is_deleted == 0,
                        )
                    )
                )
                .scalars()
                .all()
            )
            if user_rg_ids:
                stmt = (
                    stmt.join(Instance.resource_groups.of_type(ResourceGroup))
                    .where(
                        or_(
                            ResourceGroup.id.in_(user_rg_ids),
                            Instance.id.in_(privileged_instance_ids or [-1]),
                        )
                    )
                    .distinct()
                )
            elif privileged_instance_ids:
                stmt = stmt.where(Instance.id.in_(privileged_instance_ids))
            else:
                return []
        instances = list((await db.execute(stmt.order_by(Instance.instance_name))).scalars().all())

        items: list[dict[str, Any]] = []
        for inst in instances:
            cfg = (
                await db.execute(
                    select(MonitorCollectConfig).where(MonitorCollectConfig.instance_id == inst.id)
                )
            ).scalar_one_or_none()
            latest = await MonitorService.get_latest_snapshot(db, inst.id)
            health = MonitorService.evaluate_health(latest, cfg.last_collect_status if cfg else "not_configured")
            items.append(
                {
                    "instance_id": inst.id,
                    "instance_name": inst.instance_name,
                    "db_type": inst.db_type,
                    "is_active": inst.is_active,
                    "config_id": cfg.id if cfg else None,
                    "config_enabled": bool(cfg and cfg.is_enabled),
                    "collect_interval": cfg.collect_interval if cfg else None,
                    "capacity_collect_interval": cfg.capacity_collect_interval if cfg else None,
                    "retention_days": cfg.retention_days if cfg else None,
                    "last_metric_collect_at": cfg.last_metric_collect_at.isoformat()
                    if cfg and cfg.last_metric_collect_at
                    else None,
                    "last_capacity_collect_at": cfg.last_capacity_collect_at.isoformat()
                    if cfg and cfg.last_capacity_collect_at
                    else None,
                    "last_collect_status": cfg.last_collect_status if cfg else "not_configured",
                    "last_collect_error": cfg.last_collect_error if cfg else "",
                    "latest": latest,
                    **health,
                }
            )
        return sorted(items, key=lambda item: (item["health_score"], item["instance_name"]))

    @staticmethod
    async def get_latest_snapshot(db: AsyncSession, instance_id: int) -> dict[str, Any] | None:
        snap = (
            await db.execute(
                select(MonitorMetricSnapshot)
                .where(MonitorMetricSnapshot.instance_id == instance_id)
                .order_by(MonitorMetricSnapshot.collected_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not snap:
            return None
        return MonitorService._snapshot_to_dict(snap)

    @staticmethod
    def _snapshot_to_dict(snap: MonitorMetricSnapshot) -> dict[str, Any]:
        extra_metrics = snap.extra_metrics or {}
        data = {
            "instance_id": snap.instance_id,
            "collected_at": snap.collected_at.isoformat() if snap.collected_at else None,
            "status": snap.status,
            "error": snap.error,
            "missing_groups": snap.missing_groups or {},
            "is_up": snap.is_up,
            "version": snap.version,
            "uptime_seconds": snap.uptime_seconds,
            "current_connections": snap.current_connections,
            "active_sessions": snap.active_sessions,
            "max_connections": snap.max_connections,
            "connection_usage": snap.connection_usage,
            "qps": snap.qps,
            "tps": snap.tps,
            "slow_queries": snap.slow_queries,
            "error_count": snap.error_count,
            "lock_waits": snap.lock_waits,
            "long_transactions": snap.long_transactions,
            "replication_lag_seconds": snap.replication_lag_seconds,
            "total_size_bytes": snap.total_size_bytes,
            "extra_metrics": extra_metrics,
            "metric_groups": MonitorService._extract_metric_groups(extra_metrics),
        }
        data.update(MonitorService.evaluate_health(data, snap.status))
        return data

    @staticmethod
    def _extract_metric_groups(extra_metrics: dict[str, Any] | None) -> dict[str, Any]:
        """
        Expose engine-specific metrics through one stable API field.

        Engines may either return groups at the top level (current behavior) or nest
        future groups under metric_groups. The frontend consumes this normalized map
        for engine panels while generic monitor fields stay on the snapshot itself.
        """
        if not isinstance(extra_metrics, dict):
            return {}
        groups: dict[str, Any] = {}
        nested_groups = extra_metrics.get("metric_groups")
        if isinstance(nested_groups, dict):
            groups.update(nested_groups)
        for key, value in extra_metrics.items():
            if key in MonitorService.METRIC_GROUP_META_KEYS:
                continue
            groups[key] = value
        return cast(dict[str, Any], MonitorService._json_safe(groups))

    @staticmethod
    def evaluate_health(snapshot: dict[str, Any] | None, collect_status: str = "not_configured") -> dict[str, Any]:
        """根据最新原生快照推导面向运维人员的健康评分。"""
        score = 100
        reasons: list[str] = []
        if not snapshot:
            return {
                "health_score": 0,
                "risk_level": "critical" if collect_status == "failed" else "attention",
                "risk_label": "严重" if collect_status == "failed" else "关注",
                "risk_reasons": ["暂无监控快照" if collect_status != "failed" else "最近采集失败"],
            }

        extra = snapshot.get("extra_metrics") or {}
        missing_groups = snapshot.get("missing_groups") or {}
        if not snapshot.get("is_up"):
            score -= 50
            reasons.append("实例不可用或连通性未知")
        if collect_status == "failed" or snapshot.get("status") == "failed":
            score -= 35
            reasons.append("最近采集失败")
        elif missing_groups:
            score -= min(20, 5 * len(missing_groups))
            reasons.append(f"缺失 {len(missing_groups)} 个指标组")

        usage = snapshot.get("connection_usage")
        if usage is not None:
            pct = round(float(usage) * 100)
            if usage >= 0.9:
                score -= 25
                reasons.append(f"连接使用率 {pct}%")
            elif usage >= 0.75:
                score -= 12
                reasons.append(f"连接使用率 {pct}%")

        memory_usage = MonitorService._coerce_float((extra.get("memory") or {}).get("memory_usage"))
        if memory_usage is not None:
            pct = round(memory_usage * 100)
            if memory_usage >= 0.9:
                score -= 25
                reasons.append(f"内存使用率 {pct}%")
            elif memory_usage >= 0.75:
                score -= 12
                reasons.append(f"内存使用率 {pct}%")

        engine_stats = extra.get("stats") or {}
        hit_rate = MonitorService._coerce_float(engine_stats.get("keyspace_hit_rate"))
        if hit_rate is not None and hit_rate < 0.8:
            score -= 8
            reasons.append(f"缓存命中率 {round(hit_rate * 100)}%")
        evicted_keys = MonitorService._coerce_float(engine_stats.get("evicted_keys"))
        if evicted_keys and evicted_keys > 0:
            score -= 8
            reasons.append(f"Redis 已发生 {int(evicted_keys)} 次 Key 淘汰")
        delayed_inserts = MonitorService._coerce_float(engine_stats.get("delayed_inserts"))
        rejected_inserts = MonitorService._coerce_float(engine_stats.get("rejected_inserts"))
        if delayed_inserts and delayed_inserts > 0:
            score -= 8
            reasons.append(f"ClickHouse 延迟写入 {int(delayed_inserts)}")
        if rejected_inserts and rejected_inserts > 0:
            score -= 12
            reasons.append(f"ClickHouse 拒绝写入 {int(rejected_inserts)}")

        lock_waits = int(snapshot.get("lock_waits") or 0)
        if lock_waits > 0:
            score -= min(20, 8 + lock_waits * 2)
            reasons.append(f"存在 {lock_waits} 个锁等待/阻塞")

        long_transactions = int(snapshot.get("long_transactions") or 0)
        if long_transactions > 0:
            score -= min(16, 6 + long_transactions * 2)
            reasons.append(f"存在 {long_transactions} 个长事务")

        slow_queries = int(snapshot.get("slow_queries") or 0)
        if slow_queries > 0:
            score -= min(12, 4 + slow_queries // 10)
            reasons.append(f"当前慢查询 {slow_queries}")

        lag = snapshot.get("replication_lag_seconds")
        if lag is not None and float(lag) > 0:
            if float(lag) >= 300:
                score -= 25
            elif float(lag) >= 60:
                score -= 12
            else:
                score -= 5
            reasons.append(f"复制延迟 {int(float(lag))}s")

        for item in extra.get("tablespaces") or []:
            usage_pct = MonitorService._coerce_float(item.get("used_pct"))
            name = item.get("tablespace_name") or item.get("name") or "表空间"
            if usage_pct is not None and usage_pct >= 90:
                score -= 20
                reasons.append(f"{name} 表空间 {round(usage_pct)}%")
                break
            if usage_pct is not None and usage_pct >= 80:
                score -= 10
                reasons.append(f"{name} 表空间 {round(usage_pct)}%")
                break

        for item in extra.get("disks") or []:
            usage_pct = MonitorService._coerce_float(item.get("used_pct"))
            name = item.get("name") or "磁盘"
            if usage_pct is not None and usage_pct >= 90:
                score -= 20
                reasons.append(f"{name} 磁盘 {round(usage_pct)}%")
                break
            if usage_pct is not None and usage_pct >= 80:
                score -= 10
                reasons.append(f"{name} 磁盘 {round(usage_pct)}%")
                break

        fra = extra.get("fra") or {}
        fra_pct = MonitorService._coerce_float(fra.get("used_pct"))
        if fra_pct is not None and fra_pct >= 90:
            score -= 20
            reasons.append(f"FRA 使用率 {round(fra_pct)}%")
        elif fra_pct is not None and fra_pct >= 80:
            score -= 10
            reasons.append(f"FRA 使用率 {round(fra_pct)}%")

        score = max(0, min(100, score))
        if score < 40:
            level = "critical"
        elif score < 65:
            level = "warning"
        elif score < 85:
            level = "attention"
        else:
            level = "healthy"
        return {
            "health_score": score,
            "risk_level": level,
            "risk_label": MonitorService.RISK_LABELS[level],
            "risk_reasons": reasons or ["暂无明显风险"],
        }

    @staticmethod
    async def get_native_detail(db: AsyncSession, instance_id: int, user: dict[str, Any]) -> dict[str, Any]:
        instance = (
            await db.execute(
                select(Instance)
                .options(selectinload(Instance.resource_groups))
                .where(Instance.id == instance_id)
            )
        ).scalar_one_or_none()
        if not instance:
            raise NotFoundException(f"实例 ID={instance_id} 不存在")
        if not await MonitorService.check_privilege(db, user, instance_id):
            raise AppException("没有该实例的监控查看权限", code=403)

        cfg = (
            await db.execute(
                select(MonitorCollectConfig).where(MonitorCollectConfig.instance_id == instance_id)
            )
        ).scalar_one_or_none()
        latest = await MonitorService.get_latest_snapshot(db, instance_id)
        return {
            "instance": {
                "id": instance.id,
                "instance_name": instance.instance_name,
                "db_type": instance.db_type,
                "host": instance.host,
                "port": instance.port,
                "is_active": instance.is_active,
            },
            "config": {
                "id": cfg.id,
                "is_enabled": cfg.is_enabled,
                "collect_interval": cfg.collect_interval,
                "capacity_collect_interval": cfg.capacity_collect_interval,
                "retention_days": cfg.retention_days,
                "last_metric_collect_at": cfg.last_metric_collect_at.isoformat()
                if cfg.last_metric_collect_at
                else None,
                "last_capacity_collect_at": cfg.last_capacity_collect_at.isoformat()
                if cfg.last_capacity_collect_at
                else None,
                "last_collect_status": cfg.last_collect_status,
                "last_collect_error": cfg.last_collect_error,
            }
            if cfg
            else None,
            "latest": latest,
        }

    @staticmethod
    async def get_native_trend(
        db: AsyncSession, instance_id: int, user: dict[str, Any], hours: int = 24
    ) -> list[dict[str, Any]]:
        if not await MonitorService.check_privilege(db, user, instance_id):
            raise AppException("没有该实例的监控查看权限", code=403)
        instance = (
            await db.execute(select(Instance).where(Instance.id == instance_id))
        ).scalar_one_or_none()
        if not instance:
            raise NotFoundException(f"实例 ID={instance_id} 不存在")
        since = datetime.now(UTC) - timedelta(hours=hours)
        previous_total: int | None = None
        if instance.db_type == "mysql":
            previous = (
                (
                    await db.execute(
                        select(MonitorMetricSnapshot)
                        .where(
                            MonitorMetricSnapshot.instance_id == instance_id,
                            MonitorMetricSnapshot.collected_at < since,
                        )
                        .order_by(MonitorMetricSnapshot.collected_at.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
            previous_total = MonitorService._mysql_slow_query_total(previous)
        rows = (
            (
                await db.execute(
                    select(MonitorMetricSnapshot)
                    .where(
                        MonitorMetricSnapshot.instance_id == instance_id,
                        MonitorMetricSnapshot.collected_at >= since,
                    )
                    .order_by(MonitorMetricSnapshot.collected_at)
                )
            )
            .scalars()
            .all()
        )
        items: list[dict[str, Any]] = []
        for row in rows:
            slow_queries = row.slow_queries
            if instance.db_type == "mysql":
                slow_queries, previous_total = MonitorService._mysql_trend_slow_queries(
                    row, previous_total
                )
            items.append(
                {
                    "collected_at": row.collected_at.isoformat(),
                    "current_connections": row.current_connections,
                    "qps": row.qps,
                    "tps": row.tps,
                    "slow_queries": slow_queries,
                    "total_size_bytes": row.total_size_bytes,
                }
            )
        return items

    @staticmethod
    def _mysql_slow_query_total(snapshot: Any | None) -> int | None:
        if snapshot is None:
            return None
        extra = getattr(snapshot, "extra_metrics", None) or {}
        stats = extra.get("stats") if isinstance(extra, dict) else {}
        if not isinstance(stats, dict):
            return None
        lowered = {str(k).lower(): v for k, v in stats.items()}
        total = MonitorService._coerce_float(lowered.get("slow_queries_total"))
        if total is not None:
            return int(total)

        # 兼容旧采集快照：旧版 stats.slow_queries 存的是 MySQL Slow_queries 累计值；
        # 新版 stats.slow_queries 是当前态，且会同时带 slow_queries_total。
        if "lock_waits" in lowered or "innodb_row_lock_waits_total" in lowered:
            return None
        legacy_total = MonitorService._coerce_float(lowered.get("slow_queries"))
        return int(legacy_total) if legacy_total is not None else None

    @staticmethod
    def _mysql_trend_slow_queries(
        snapshot: MonitorMetricSnapshot,
        previous_total: int | None,
    ) -> tuple[int | None, int | None]:
        current_total = MonitorService._mysql_slow_query_total(snapshot)
        if current_total is None:
            return snapshot.slow_queries, previous_total
        if previous_total is None or current_total < previous_total:
            return 0, current_total
        return current_total - previous_total, current_total

    @staticmethod
    async def get_database_capacity(db: AsyncSession, instance_id: int, user: dict[str, Any]) -> list[dict[str, Any]]:
        if not await MonitorService.check_privilege(db, user, instance_id):
            raise AppException("没有该实例的监控查看权限", code=403)
        return await MonitorCapacityService.database_capacity(db, instance_id)

    @staticmethod
    async def get_table_capacity(
        db: AsyncSession,
        instance_id: int,
        user: dict[str, Any],
        db_name: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[int, list[dict[str, Any]]]:
        if not await MonitorService.check_privilege(db, user, instance_id):
            raise AppException("没有该实例的监控查看权限", code=403)
        return await MonitorCapacityService.table_capacity(
            db, instance_id, db_name=db_name, search=search, page=page, page_size=page_size
        )

    @staticmethod
    async def get_native_overview(db: AsyncSession, user: dict[str, Any]) -> dict[str, Any]:
        items = await MonitorService.list_native_instances(db, user)
        total = len(items)
        online = sum(1 for item in items if (item.get("latest") or {}).get("is_up"))
        failed = sum(1 for item in items if item.get("last_collect_status") == "failed")
        high_connection = sum(
            1 for item in items if ((item.get("latest") or {}).get("connection_usage") or 0) >= 0.8
        )
        capacity_risk = sum(
            1 for item in items if MonitorService._has_capacity_risk(item.get("latest") or {})
        )
        replication_risk = sum(
            1 for item in items if ((item.get("latest") or {}).get("replication_lag_seconds") or 0) >= 60
        )
        lock_risk = sum(
            1
            for item in items
            if ((item.get("latest") or {}).get("lock_waits") or 0) > 0
            or ((item.get("latest") or {}).get("long_transactions") or 0) > 0
        )
        by_db_type: dict[str, int] = {}
        by_risk_level: dict[str, int] = {}
        for item in items:
            by_db_type[item["db_type"]] = by_db_type.get(item["db_type"], 0) + 1
            level = item.get("risk_level", "attention")
            by_risk_level[level] = by_risk_level.get(level, 0) + 1
        return {
            "cards": {
                "instance_total": total,
                "online_count": online,
                "online_rate": round(online / total, 4) if total else 0,
                "abnormal_count": sum(1 for item in items if item.get("risk_level") in {"warning", "critical"}),
                "collect_failed_count": failed,
                "high_connection_count": high_connection,
                "capacity_risk_count": capacity_risk,
                "replication_lag_count": replication_risk,
                "lock_or_long_tx_count": lock_risk,
            },
            "distributions": {"db_type": by_db_type, "risk_level": by_risk_level},
            "items": items,
        }

    @staticmethod
    def _has_capacity_risk(snapshot: dict[str, Any]) -> bool:
        return MonitorCapacityService.has_capacity_risk(snapshot)

    @staticmethod
    async def get_native_health(db: AsyncSession, instance_id: int, user: dict[str, Any]) -> dict[str, Any]:
        detail = await MonitorService.get_native_detail(db, instance_id, user)
        latest = detail.get("latest")
        return {
            "instance": detail["instance"],
            **MonitorService.evaluate_health(
                latest, (detail.get("config") or {}).get("last_collect_status", "not_configured")
            ),
            "latest": latest,
        }

    @staticmethod
    async def get_engine_detail(db: AsyncSession, instance_id: int, user: dict[str, Any]) -> dict[str, Any]:
        detail = await MonitorService.get_native_detail(db, instance_id, user)
        latest = detail.get("latest") or {}
        extra = latest.get("extra_metrics") or {}
        return {
            "instance": detail["instance"],
            "metric_groups": MonitorService._extract_metric_groups(extra),
            "missing_groups": latest.get("missing_groups") or {},
            "health": MonitorService.evaluate_health(
                latest, (detail.get("config") or {}).get("last_collect_status", "not_configured")
            ),
        }

    @staticmethod
    async def get_alert_rules(db: AsyncSession, instance_id: int, user: dict[str, Any]) -> dict[str, Any]:
        detail = await MonitorService.get_native_detail(db, instance_id, user)
        cfg = (
            await db.execute(
                select(MonitorCollectConfig).where(MonitorCollectConfig.instance_id == instance_id)
            )
        ).scalar_one_or_none()
        return {
            "instance": detail["instance"],
            "rules": (cfg.alert_rules_override if cfg else {}) or {},
            "defaults": {
                "connection_usage": {"operator": ">=", "threshold": 0.8, "duration_count": 3},
                "memory_usage": {"operator": ">=", "threshold": 0.85, "duration_count": 2},
                "redis_keyspace_hit_rate": {"operator": "<", "threshold": 0.8, "duration_count": 3},
                "clickhouse_disk_used_pct": {"operator": ">=", "threshold": 85, "duration_count": 1},
                "replication_lag_seconds": {"operator": ">=", "threshold": 60, "duration_count": 2},
                "tablespace_used_pct": {"operator": ">=", "threshold": 85, "duration_count": 1},
                "fra_used_pct": {"operator": ">=", "threshold": 85, "duration_count": 1},
                "lock_waits": {"operator": ">", "threshold": 0, "duration_count": 1},
            },
        }

    @staticmethod
    async def update_alert_rules(
        db: AsyncSession, instance_id: int, rules: dict[str, Any], user: dict[str, Any]
    ) -> dict[str, Any]:
        inst_result = await db.execute(
            select(Instance)
            .options(selectinload(Instance.resource_groups))
            .where(Instance.id == instance_id)
        )
        instance = inst_result.scalar_one_or_none()
        if not instance:
            raise NotFoundException(f"实例 ID={instance_id} 不存在")
        if not MonitorService._can_access_instance(user, instance):
            raise AppException("不能修改资源组外实例的监控告警规则", code=403)
        cfg = (
            await db.execute(
                select(MonitorCollectConfig).where(MonitorCollectConfig.instance_id == instance_id)
            )
        ).scalar_one_or_none()
        if not cfg:
            cfg = MonitorCollectConfig(
                instance_id=instance_id,
                exporter_url="",
                exporter_type="",
                created_by=user.get("username", ""),
            )
            db.add(cfg)
        cfg.alert_rules_override = MonitorService._json_safe(rules)
        await db.commit()
        await db.refresh(cfg)
        return {"rules": cfg.alert_rules_override or {}}

    @staticmethod
    def _alert_rule_defaults() -> dict[str, dict[str, Any]]:
        return MonitorAlertService.alert_rule_defaults()

    @staticmethod
    def _metric_for_alert(snapshot: MonitorMetricSnapshot, rule_key: str) -> float | None:
        return MonitorAlertService.metric_for_alert(snapshot, rule_key)

    @staticmethod
    def _compare_alert_value(value: float, operator: str, threshold: float) -> bool:
        return MonitorAlertService.compare_alert_value(value, operator, threshold)

    @staticmethod
    async def sync_alert_events_for_snapshot(
        db: AsyncSession,
        inst: Instance,
        cfg: MonitorCollectConfig,
        snapshot: MonitorMetricSnapshot,
    ) -> None:
        await MonitorAlertService.sync_alert_events_for_snapshot(db, inst, cfg, snapshot)

    @staticmethod
    def _alert_event_to_dict(event: MonitorAlertEvent, instance_name: str = "", db_type: str = "") -> dict[str, Any]:
        return MonitorAlertService.alert_event_to_dict(event, instance_name, db_type)

    @staticmethod
    async def list_alert_events(
        db: AsyncSession,
        user: dict[str, Any],
        status: str | None = None,
        instance_id: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[int, list[dict[str, Any]]]:
        return await MonitorAlertService.list_alert_events(
            db, user, status=status, instance_id=instance_id, page=page, page_size=page_size
        )

    @staticmethod
    async def get_alert_event(db: AsyncSession, event_id: int, user: dict[str, Any]) -> dict[str, Any]:
        return await MonitorAlertService.get_alert_event(db, event_id, user)

    @staticmethod
    async def change_alert_event(
        db: AsyncSession,
        event_id: int,
        action: str,
        user: dict[str, Any],
        *,
        minutes: int = 60,
        reason: str = "",
    ) -> dict[str, Any]:
        return await MonitorAlertService.change_alert_event(
            db, event_id, action, user, minutes=minutes, reason=reason
        )

    @staticmethod
    async def get_waits(db: AsyncSession, instance_id: int, user: dict[str, Any]) -> dict[str, Any]:
        detail = await MonitorService.get_native_detail(db, instance_id, user)
        extra = (detail.get("latest") or {}).get("extra_metrics") or {}
        return {
            "top_waits": extra.get("active_wait_events") or extra.get("wait_events") or extra.get("waits") or [],
            "blocking_sessions": extra.get("blocking_sessions") or [],
            "long_transactions": extra.get("long_transactions") or [],
            "missing_groups": (detail.get("latest") or {}).get("missing_groups") or {},
        }

    @staticmethod
    async def get_top_sql(
        db: AsyncSession,
        instance_id: int,
        user: dict[str, Any],
        limit: int = 20,
        window_minutes: int = 30,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> dict[str, Any]:
        from app.engines.registry import get_engine

        if not await MonitorService.check_privilege(db, user, instance_id):
            raise AppException("没有该实例的监控查看权限", code=403)
        inst = (await db.execute(select(Instance).where(Instance.id == instance_id))).scalar_one_or_none()
        if not inst:
            raise NotFoundException(f"实例 ID={instance_id} 不存在")
        window_minutes = max(1, min(int(window_minutes or 30), 1440))
        custom_range = date_start is not None and date_end is not None and date_start < date_end
        if custom_range:
            assert date_start is not None and date_end is not None
            window_minutes = max(1, int((date_end - date_start).total_seconds() // 60) or 1)
        latest = await MonitorService.get_latest_snapshot(db, instance_id)
        extra = (latest or {}).get("extra_metrics") or {}
        db_type = inst.db_type.lower()
        is_tidb = db_type == "tidb"
        is_oracle = db_type == "oracle"
        items = [] if is_tidb or is_oracle else extra.get("top_sql") or []
        error = ""
        if is_tidb:
            engine = get_engine(inst)
            collect_top_sql = getattr(engine, "collect_top_sql", None)
            if callable(collect_top_sql):
                if custom_range:
                    rs = await collect_top_sql(
                        limit=limit,
                        window_minutes=window_minutes,
                        start_time=date_start,
                        end_time=date_end,
                    )
                else:
                    rs = await collect_top_sql(limit=limit, window_minutes=window_minutes)
                error = rs.error
                if rs.is_success:
                    items = MonitorService._result_rows_to_dicts(rs.column_list, rs.rows)
            if not items and extra.get("top_sql"):
                items = extra.get("top_sql") or []
        elif is_oracle or not items:
            engine = get_engine(inst)
            tried_activity = False
            if (
                db_type in MonitorService.ACTIVITY_TOP_SQL_TYPES
                and hasattr(engine, "collect_sql_activity")
            ):
                tried_activity = True
                if is_oracle:
                    rs = await engine.collect_sql_activity(
                        limit=limit,
                        min_duration_ms=0,
                        window_minutes=window_minutes,
                        start_time=date_start if custom_range else None,
                        end_time=date_end if custom_range else None,
                    )
                else:
                    rs = await engine.collect_sql_activity(limit=limit)
                error = rs.error or getattr(rs, "warning", "")
                if rs.is_success:
                    items = MonitorService._result_rows_to_dicts(rs.column_list, rs.rows)
            if is_oracle and not items and extra.get("top_sql"):
                items = extra.get("top_sql") or []
            elif not tried_activity and hasattr(engine, "collect_slow_queries"):
                rs = await engine.collect_slow_queries(limit=limit)
                error = rs.error or getattr(rs, "warning", "")
                if rs.is_success:
                    items = MonitorService._result_rows_to_dicts(rs.column_list, rs.rows)
        return {
            "items": items[:limit],
            "error": error,
            "window_minutes": window_minutes,
            "date_start": date_start.isoformat() if custom_range and date_start is not None else None,
            "date_end": date_end.isoformat() if custom_range and date_end is not None else None,
            "missing_groups": (latest or {}).get("missing_groups") or {},
        }

    @staticmethod
    def _result_rows_to_dicts(columns: list[str], rows: list[Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                result.append(MonitorService._json_safe(row))
            elif columns:
                result.append(MonitorService._json_safe(dict(zip(columns, row, strict=False))))
            else:
                result.append({"value": MonitorService._json_safe(row)})
        return result

    @staticmethod
    async def get_capacity_growth(
        db: AsyncSession, instance_id: int, user: dict[str, Any], days: int = 7
    ) -> dict[str, Any]:
        if not await MonitorService.check_privilege(db, user, instance_id):
            raise AppException("没有该实例的监控查看权限", code=403)
        return await MonitorCapacityService.capacity_growth(db, instance_id, days=days)

    @staticmethod
    async def collect_due_native(db: AsyncSession, limit: int | None = None) -> dict[str, Any]:
        return await MonitorCollectService.collect_due_native(db, limit=limit)

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
            return {str(k): MonitorService._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [MonitorService._json_safe(v) for v in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return int(value) if value == value.to_integral_value() else float(value)
        return value
