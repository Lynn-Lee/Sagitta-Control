"""观测中心 + Dashboard 统计服务（Sprint 5）。"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.models.instance import Instance, InstanceDatabase
from app.models.monitor import (
    MonitorAlertEvent,
    MonitorCollectConfig,
    MonitorDatabaseCapacitySnapshot,
    MonitorMetricSnapshot,
    MonitorPrivilege,
    MonitorPrivilegeApply,
    MonitorTableCapacitySnapshot,
)
from app.models.user import ResourceGroup, Users
from app.schemas.monitor import (
    MonitorConfigCreate,
    MonitorConfigUpdate,
    NativeMonitorConfigUpsert,
)
from app.services.dashboard import DashboardService
from app.services.monitor_alerts import MonitorAlertService

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
    SYSTEM_DATABASES = {
        "information_schema",
        "performance_schema",
        "mysql",
        "sys",
        "pg_catalog",
        "template0",
        "template1",
        "admin",
        "local",
        "config",
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
    def _can_access_instance(user: dict, instance: Instance) -> bool:
        # 观测域实例访问判定统一收敛到 MonitorAlertService，避免两处重复实现漂移
        return MonitorAlertService._can_access_instance(user, instance)

    @staticmethod
    async def list_configs(
        db: AsyncSession,
        user: dict,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[int, list[dict]]:
        query = select(MonitorCollectConfig, Instance.instance_name).join(
            Instance, MonitorCollectConfig.instance_id == Instance.id
        )
        if not (user.get("is_superuser") or "observability_instance_all" in user.get("permissions", [])):
            user_rg_ids = user.get("resource_groups", [])
            if not user_rg_ids:
                return 0, []
            from app.models.user import ResourceGroup

            query = (
                query.join(Instance.resource_groups.of_type(ResourceGroup))
                .where(ResourceGroup.id.in_(user_rg_ids))
                .distinct()
            )

        total_q = await db.execute(select(func.count()).select_from(query.subquery()))
        total = total_q.scalar_one()
        result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
        items = []
        for cfg, inst_name in result:
            items.append(
                {
                    "id": cfg.id,
                    "instance_id": cfg.instance_id,
                    "instance_name": inst_name,
                    "is_enabled": cfg.is_enabled,
                    "collect_interval": cfg.collect_interval,
                    "exporter_url": cfg.exporter_url,
                    "exporter_type": cfg.exporter_type,
                    "alert_rules_override": cfg.alert_rules_override or {},
                    "created_by": cfg.created_by,
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
            )
        return total, items

    @staticmethod
    async def create_config(
        db: AsyncSession, data: MonitorConfigCreate, operator: dict
    ) -> MonitorCollectConfig:
        inst = await db.execute(
            select(Instance)
            .options(selectinload(Instance.resource_groups))
            .where(Instance.id == data.instance_id)
        )
        instance = inst.scalar_one_or_none()
        if not instance:
            raise NotFoundException(f"实例 ID={data.instance_id} 不存在")
        if not MonitorService._can_access_instance(operator, instance):
            raise AppException("不能为资源组外实例配置监控", code=403)
        existing = await db.execute(
            select(MonitorCollectConfig).where(MonitorCollectConfig.instance_id == data.instance_id)
        )
        if existing.scalar_one_or_none():
            raise ConflictException(f"实例 ID={data.instance_id} 已有采集配置")
        cfg = MonitorCollectConfig(
            instance_id=data.instance_id,
            exporter_url=data.exporter_url,
            exporter_type=data.exporter_type,
            collect_interval=data.collect_interval,
            capacity_collect_interval=data.capacity_collect_interval,
            retention_days=data.retention_days,
            alert_rules_override=data.alert_rules_override,
            created_by=operator.get("username", ""),
        )
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
        return cfg

    @staticmethod
    async def update_config_with_access(
        db: AsyncSession,
        config_id: int,
        data: MonitorConfigUpdate,
        user: dict,
    ) -> MonitorCollectConfig:
        result = await db.execute(
            select(MonitorCollectConfig, Instance)
            .join(Instance, MonitorCollectConfig.instance_id == Instance.id)
            .options(selectinload(Instance.resource_groups))
            .where(MonitorCollectConfig.id == config_id)
        )
        row = result.first()
        if not row:
            raise NotFoundException(f"采集配置 ID={config_id} 不存在")
        cfg, instance = row
        if not MonitorService._can_access_instance(user, instance):
            raise AppException("不能修改资源组外实例的监控配置", code=403)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(cfg, field, value)
        await db.commit()
        await db.refresh(cfg)
        return cfg

    @staticmethod
    async def delete_config(db: AsyncSession, config_id: int, user: dict) -> None:
        result = await db.execute(
            select(MonitorCollectConfig, Instance)
            .join(Instance, MonitorCollectConfig.instance_id == Instance.id)
            .options(selectinload(Instance.resource_groups))
            .where(MonitorCollectConfig.id == config_id)
        )
        row = result.first()
        if not row:
            raise NotFoundException(f"采集配置 ID={config_id} 不存在")
        cfg, instance = row
        if not MonitorService._can_access_instance(user, instance):
            raise AppException("不能删除资源组外实例的监控配置", code=403)
        await db.delete(cfg)
        await db.commit()

    @staticmethod
    async def get_sd_targets(db: AsyncSession) -> list[dict]:
        """Prometheus HTTP SD 格式 targets。"""
        result = await db.execute(
            select(MonitorCollectConfig, Instance)
            .join(Instance, MonitorCollectConfig.instance_id == Instance.id)
            .where(MonitorCollectConfig.is_enabled)
        )
        targets = []
        for cfg, inst in result:
            url = cfg.exporter_url
            host_part = url.split("//")[-1].split("/")[0]
            path_part = (
                "/" + "/".join(url.split("//")[-1].split("/")[1:])
                if "/" in url.split("//")[-1]
                else "/metrics"
            )
            targets.append(
                {
                    "targets": [host_part],
                    "labels": {
                        "__metrics_path__": path_part,
                        "__scrape_interval__": f"{cfg.collect_interval}s",
                        "job": cfg.exporter_type,
                        "instance_id": str(inst.id),
                        "instance_name": inst.instance_name,
                        "db_type": inst.db_type,
                    },
                }
            )
        return targets

    @staticmethod
    async def apply_privilege(db: AsyncSession, data, user: dict) -> MonitorPrivilegeApply:
        apply = MonitorPrivilegeApply(
            title=data.title,
            user_id=user["id"],
            instance_id=data.instance_id,
            group_id=data.group_id,
            valid_date=data.valid_date,
            apply_reason=data.apply_reason,
            audit_auth_groups=data.audit_auth_groups or str(data.group_id),
            status=0,
        )
        db.add(apply)
        await db.commit()
        await db.refresh(apply)
        from app.services.notify import NotifyService

        instance = await db.get(Instance, apply.instance_id)
        NotifyService.enqueue_event(
            {
                "event_type": "approval_pending",
                "subject_type": "monitor_privilege",
                "subject_id": apply.id,
                "app_type": "监控权限申请",
                "title": apply.title,
                "applicant_id": apply.user_id,
                "applicant_name": user.get("display_name") or user.get("username") or str(apply.user_id),
                "instance_id": apply.instance_id,
                "instance_name": instance.instance_name if instance else "",
                "permission": "observability_collect_manage",
                "exclude_user_ids": [apply.user_id],
                "remark": "监控权限申请已提交，待审批",
                "detail_path": "/monitor",
            }
        )
        return apply

    @staticmethod
    async def audit_privilege(
        db: AsyncSession, apply_id: int, action: str, operator: dict, remark: str = ""
    ) -> MonitorPrivilegeApply:
        result = await db.execute(
            select(MonitorPrivilegeApply).where(MonitorPrivilegeApply.id == apply_id)
        )
        apply = result.scalar_one_or_none()
        if not apply:
            raise NotFoundException(f"申请 ID={apply_id} 不存在")
        if apply.status != 0:
            raise AppException("该申请已审批", code=400)
        if action == "pass":
            apply.status = 1
            db.add(
                MonitorPrivilege(
                    apply_id=apply.id,
                    user_id=apply.user_id,
                    instance_id=apply.instance_id,
                    valid_date=apply.valid_date,
                    is_deleted=0,
                )
            )
        else:
            apply.status = 2
        await db.commit()
        await db.refresh(apply)
        from app.services.notify import NotifyService

        applicant = await db.get(Users, apply.user_id)
        instance = await db.get(Instance, apply.instance_id)
        NotifyService.enqueue_event(
            {
                "event_type": "approval_passed" if action == "pass" else "approval_rejected",
                "subject_type": "monitor_privilege",
                "subject_id": apply.id,
                "app_type": "监控权限申请",
                "title": apply.title,
                "applicant_id": apply.user_id,
                "applicant_name": (applicant.display_name or applicant.username) if applicant else str(apply.user_id),
                "user_ids": [apply.user_id],
                "instance_id": apply.instance_id,
                "instance_name": instance.instance_name if instance else "",
                "operator_name": operator.get("display_name") or operator.get("username") or "",
                "remark": remark or ("监控权限申请已审批通过" if action == "pass" else "监控权限申请已驳回"),
                "detail_path": "/monitor",
            }
        )
        return apply

    @staticmethod
    async def check_privilege(db: AsyncSession, user: dict, instance_id: int) -> bool:
        if user.get("is_superuser") or "observability_instance_all" in user.get("permissions", []):
            return True
        instance_result = await db.execute(
            select(Instance)
            .options(selectinload(Instance.resource_groups))
            .where(Instance.id == instance_id, Instance.is_active.is_(True))
        )
        instance = instance_result.scalar_one_or_none()
        if not instance:
            return False
        if MonitorService._can_access_instance(user, instance):
            return True

        result = await db.execute(
            select(MonitorPrivilege).where(
                and_(
                    MonitorPrivilege.user_id == user["id"],
                    MonitorPrivilege.instance_id == instance_id,
                    MonitorPrivilege.valid_date >= date.today(),
                    MonitorPrivilege.is_deleted == 0,
                )
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def list_applies(
        db: AsyncSession, user: dict, status: int | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[int, list]:
        query = select(MonitorPrivilegeApply)
        if not user.get("is_superuser") and "observability_collect_manage" not in user.get("permissions", []):
            query = query.where(MonitorPrivilegeApply.user_id == user["id"])
        if status is not None:
            query = query.where(MonitorPrivilegeApply.status == status)
        total_q = await db.execute(select(func.count()).select_from(query.subquery()))
        total = total_q.scalar_one()
        result = await db.execute(
            query.order_by(MonitorPrivilegeApply.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return total, list(result.scalars().all())

    @staticmethod
    async def upsert_native_config(
        db: AsyncSession,
        instance_id: int,
        data: Any,
        user: dict,
    ) -> MonitorCollectConfig:
        inst_result = await db.execute(
            select(Instance)
            .options(selectinload(Instance.resource_groups))
            .where(Instance.id == instance_id)
        )
        instance = inst_result.scalar_one_or_none()
        if not instance:
            raise NotFoundException(f"实例 ID={instance_id} 不存在")
        if not MonitorService._can_access_instance(user, instance):
            raise AppException("不能配置资源组外实例的监控采集", code=403)

        cfg_result = await db.execute(
            select(MonitorCollectConfig).where(MonitorCollectConfig.instance_id == instance_id)
        )
        cfg = cfg_result.scalar_one_or_none()
        if not cfg:
            cfg = MonitorCollectConfig(
                instance_id=instance_id,
                exporter_url="",
                exporter_type="",
                created_by=user.get("username", ""),
            )
            db.add(cfg)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(cfg, field, value)
        await db.commit()
        await db.refresh(cfg)
        return cfg

    @staticmethod
    async def collect_native_now(db: AsyncSession, instance_id: int, user: dict) -> dict:
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
            snapshot = await MonitorService.collect_instance_metrics(db, inst, cfg)
            await MonitorService.collect_instance_capacity(db, inst, cfg)
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
    async def _accessible_instances(db: AsyncSession, user: dict) -> list[Instance]:
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
                    .where(or_(ResourceGroup.id.in_(user_rg_ids), Instance.id.in_(privileged_instance_ids)))
                    .distinct()
                )
            elif privileged_instance_ids:
                stmt = stmt.where(Instance.id.in_(privileged_instance_ids))
            else:
                return []
        result = await db.execute(stmt.order_by(Instance.id.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def _unified_collect_config_item(
        db: AsyncSession,
        instance: Instance,
        user: dict,
    ) -> dict[str, Any]:
        from app.models.session import SessionCollectConfig
        from app.models.slowlog import SlowQueryConfig

        native_cfg = (
            await db.execute(
                select(MonitorCollectConfig).where(MonitorCollectConfig.instance_id == instance.id)
            )
        ).scalar_one_or_none()
        session_cfg = (
            await db.execute(
                select(SessionCollectConfig).where(SessionCollectConfig.instance_id == instance.id)
            )
        ).scalar_one_or_none()
        sql_cfg = (
            await db.execute(
                select(SlowQueryConfig).where(SlowQueryConfig.instance_id == instance.id)
            )
        ).scalar_one_or_none()

        def iso(value: Any) -> str | None:
            return value.isoformat() if value else None

        return {
            "instance_id": instance.id,
            "instance_name": instance.instance_name,
            "db_type": instance.db_type,
            "native": {
                "id": native_cfg.id if native_cfg else None,
                "is_enabled": native_cfg.is_enabled if native_cfg else False,
                "collect_interval": native_cfg.collect_interval if native_cfg else 60,
                "capacity_collect_interval": native_cfg.capacity_collect_interval if native_cfg else 3600,
                "retention_days": native_cfg.retention_days if native_cfg else 30,
                "last_metric_collect_at": iso(native_cfg.last_metric_collect_at) if native_cfg else None,
                "last_capacity_collect_at": iso(native_cfg.last_capacity_collect_at) if native_cfg else None,
                "last_collect_status": native_cfg.last_collect_status if native_cfg else "not_configured",
                "last_collect_error": native_cfg.last_collect_error if native_cfg else "",
            },
            "session": {
                "id": session_cfg.id if session_cfg else None,
                "is_enabled": session_cfg.is_enabled if session_cfg else True,
                "collect_interval": session_cfg.collect_interval if session_cfg else 60,
                "retention_days": session_cfg.retention_days if session_cfg else 30,
                "last_collect_at": iso(session_cfg.last_collect_at) if session_cfg else None,
                "last_collect_status": session_cfg.last_collect_status if session_cfg else "never",
                "last_collect_error": session_cfg.last_collect_error if session_cfg else "",
                "last_collect_count": session_cfg.last_collect_count if session_cfg else 0,
            },
            "sql": {
                "id": sql_cfg.id if sql_cfg else None,
                "is_enabled": sql_cfg.is_enabled if sql_cfg else True,
                "threshold_ms": sql_cfg.threshold_ms if sql_cfg else 1000,
                "collect_interval": sql_cfg.collect_interval if sql_cfg else 300,
                "retention_days": sql_cfg.retention_days if sql_cfg else 30,
                "collect_limit": sql_cfg.collect_limit if sql_cfg else 100,
                "last_collect_at": iso(sql_cfg.last_collect_at) if sql_cfg else None,
                "last_collect_status": sql_cfg.last_collect_status if sql_cfg else "never",
                "last_collect_error": sql_cfg.last_collect_error if sql_cfg else "",
                "last_collect_count": sql_cfg.last_collect_count if sql_cfg else 0,
                "last_collect_sources": sql_cfg.last_collect_sources if sql_cfg else [],
                "last_collect_message": sql_cfg.last_collect_message if sql_cfg else "",
            },
        }

    @staticmethod
    async def list_unified_collect_configs(db: AsyncSession, user: dict) -> dict[str, Any]:
        instances = await MonitorService._accessible_instances(db, user)
        items = [
            await MonitorService._unified_collect_config_item(db, instance, user)
            for instance in instances
        ]
        return {"total": len(items), "items": items}

    @staticmethod
    async def upsert_unified_collect_config(
        db: AsyncSession,
        instance_id: int,
        data: Any,
        user: dict,
    ) -> dict[str, Any]:
        from app.schemas.diagnostic import SessionCollectConfigUpsert
        from app.schemas.slowlog import SlowQueryConfigUpsert
        from app.services.session_diagnostic import SessionDiagnosticService
        from app.services.slowlog import SlowLogService

        instance_result = await db.execute(
            select(Instance)
            .options(selectinload(Instance.resource_groups))
            .where(Instance.id == instance_id, Instance.is_active.is_(True))
        )
        instance = instance_result.scalar_one_or_none()
        if not instance:
            raise NotFoundException(f"实例 ID={instance_id} 不存在")
        if not MonitorService._can_access_instance(user, instance):
            raise AppException("不能配置资源组外实例的采集", code=403)

        await MonitorService.upsert_native_config(db, instance_id, data.native, user)
        await SessionDiagnosticService.upsert_config(
            db,
            SessionCollectConfigUpsert(instance_id=instance_id, **data.session.model_dump()),
            user,
        )
        await SlowLogService.upsert_config(
            db,
            SlowQueryConfigUpsert(instance_id=instance_id, **data.sql.model_dump()),
            user,
        )
        return await MonitorService._unified_collect_config_item(db, instance, user)

    @staticmethod
    async def bulk_upsert_unified_collect_configs(
        db: AsyncSession,
        data: Any,
        user: dict,
    ) -> dict[str, Any]:
        instances = await MonitorService._accessible_instances(db, user)
        success = 0
        failed: list[str] = []
        for instance in instances:
            try:
                await MonitorService.upsert_unified_collect_config(db, instance.id, data, user)
                success += 1
            except Exception as exc:
                failed.append(f"{instance.instance_name}: {exc}")
        return {
            "status": 0,
            "msg": f"已配置 {success}/{len(instances)} 个实例",
            "total": len(instances),
            "success": success,
            "failed": failed,
        }

    @staticmethod
    async def list_native_instances(db: AsyncSession, user: dict) -> list[dict]:
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

        items: list[dict] = []
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
    async def get_latest_snapshot(db: AsyncSession, instance_id: int) -> dict | None:
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
    def _snapshot_to_dict(snap: MonitorMetricSnapshot) -> dict:
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
        return MonitorService._json_safe(groups)

    @staticmethod
    def evaluate_health(snapshot: dict | None, collect_status: str = "not_configured") -> dict:
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
    async def get_native_detail(db: AsyncSession, instance_id: int, user: dict) -> dict:
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
        db: AsyncSession, instance_id: int, user: dict, hours: int = 24
    ) -> list[dict]:
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
        items: list[dict] = []
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
    async def get_database_capacity(db: AsyncSession, instance_id: int, user: dict) -> list[dict]:
        if not await MonitorService.check_privilege(db, user, instance_id):
            raise AppException("没有该实例的监控查看权限", code=403)
        latest_at = (
            await db.execute(
                select(func.max(MonitorDatabaseCapacitySnapshot.collected_at)).where(
                    MonitorDatabaseCapacitySnapshot.instance_id == instance_id
                )
            )
        ).scalar_one_or_none()
        if not latest_at:
            return []
        rows = (
            (
                await db.execute(
                    select(MonitorDatabaseCapacitySnapshot)
                    .where(
                        MonitorDatabaseCapacitySnapshot.instance_id == instance_id,
                        MonitorDatabaseCapacitySnapshot.collected_at == latest_at,
                    )
                    .order_by(MonitorDatabaseCapacitySnapshot.total_size_bytes.desc())
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "db_name": row.db_name,
                "collected_at": row.collected_at.isoformat(),
                "table_count": row.table_count,
                "data_size_bytes": row.data_size_bytes,
                "index_size_bytes": row.index_size_bytes,
                "total_size_bytes": row.total_size_bytes,
                "row_count": row.row_count,
                "status": row.status,
                "error": row.error,
            }
            for row in rows
        ]

    @staticmethod
    async def get_table_capacity(
        db: AsyncSession,
        instance_id: int,
        user: dict,
        db_name: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[int, list[dict]]:
        if not await MonitorService.check_privilege(db, user, instance_id):
            raise AppException("没有该实例的监控查看权限", code=403)
        latest_at = (
            await db.execute(
                select(func.max(MonitorTableCapacitySnapshot.collected_at)).where(
                    MonitorTableCapacitySnapshot.instance_id == instance_id
                )
            )
        ).scalar_one_or_none()
        if not latest_at:
            return 0, []
        stmt = select(MonitorTableCapacitySnapshot).where(
            MonitorTableCapacitySnapshot.instance_id == instance_id,
            MonitorTableCapacitySnapshot.collected_at == latest_at,
        )
        if db_name:
            stmt = stmt.where(MonitorTableCapacitySnapshot.db_name == db_name)
        if search:
            stmt = stmt.where(MonitorTableCapacitySnapshot.table_name.ilike(f"%{search}%"))
        total = int(
            (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
        )
        rows = (
            (
                await db.execute(
                    stmt.order_by(MonitorTableCapacitySnapshot.total_size_bytes.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        return total, [
            {
                "db_name": row.db_name,
                "table_name": row.table_name,
                "collected_at": row.collected_at.isoformat(),
                "data_size_bytes": row.data_size_bytes,
                "index_size_bytes": row.index_size_bytes,
                "total_size_bytes": row.total_size_bytes,
                "row_count": row.row_count,
                "extra": row.extra or {},
            }
            for row in rows
        ]

    @staticmethod
    async def get_native_overview(db: AsyncSession, user: dict) -> dict:
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
    def _has_capacity_risk(snapshot: dict) -> bool:
        extra = snapshot.get("extra_metrics") or {}
        tablespaces = extra.get("tablespaces") or []
        if any((MonitorService._coerce_float(item.get("used_pct")) or 0) >= 80 for item in tablespaces):
            return True
        disks = extra.get("disks") or []
        if any((MonitorService._coerce_float(item.get("used_pct")) or 0) >= 80 for item in disks):
            return True
        fra = extra.get("fra") or {}
        return (MonitorService._coerce_float(fra.get("used_pct")) or 0) >= 80

    @staticmethod
    async def get_native_health(db: AsyncSession, instance_id: int, user: dict) -> dict:
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
    async def get_engine_detail(db: AsyncSession, instance_id: int, user: dict) -> dict:
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
    async def get_alert_rules(db: AsyncSession, instance_id: int, user: dict) -> dict:
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
        db: AsyncSession, instance_id: int, rules: dict[str, Any], user: dict
    ) -> dict:
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
        user: dict,
        status: str | None = None,
        instance_id: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[int, list[dict[str, Any]]]:
        return await MonitorAlertService.list_alert_events(
            db, user, status=status, instance_id=instance_id, page=page, page_size=page_size
        )

    @staticmethod
    async def get_alert_event(db: AsyncSession, event_id: int, user: dict) -> dict[str, Any]:
        return await MonitorAlertService.get_alert_event(db, event_id, user)

    @staticmethod
    async def change_alert_event(
        db: AsyncSession,
        event_id: int,
        action: str,
        user: dict,
        *,
        minutes: int = 60,
        reason: str = "",
    ) -> dict[str, Any]:
        return await MonitorAlertService.change_alert_event(
            db, event_id, action, user, minutes=minutes, reason=reason
        )

    @staticmethod
    async def get_waits(db: AsyncSession, instance_id: int, user: dict) -> dict:
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
        user: dict,
        limit: int = 20,
        window_minutes: int = 30,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> dict:
        from app.engines.registry import get_engine

        if not await MonitorService.check_privilege(db, user, instance_id):
            raise AppException("没有该实例的监控查看权限", code=403)
        inst = (await db.execute(select(Instance).where(Instance.id == instance_id))).scalar_one_or_none()
        if not inst:
            raise NotFoundException(f"实例 ID={instance_id} 不存在")
        window_minutes = max(1, min(int(window_minutes or 30), 1440))
        custom_range = date_start is not None and date_end is not None and date_start < date_end
        if custom_range:
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
            "date_start": date_start.isoformat() if custom_range else None,
            "date_end": date_end.isoformat() if custom_range else None,
            "missing_groups": (latest or {}).get("missing_groups") or {},
        }

    @staticmethod
    def _result_rows_to_dicts(columns: list[str], rows: list[Any]) -> list[dict]:
        result: list[dict] = []
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
        db: AsyncSession, instance_id: int, user: dict, days: int = 7
    ) -> dict:
        if not await MonitorService.check_privilege(db, user, instance_id):
            raise AppException("没有该实例的监控查看权限", code=403)
        since = datetime.now(UTC) - timedelta(days=days)
        db_rows = (
            (
                await db.execute(
                    select(MonitorDatabaseCapacitySnapshot)
                    .where(
                        MonitorDatabaseCapacitySnapshot.instance_id == instance_id,
                        MonitorDatabaseCapacitySnapshot.collected_at >= since,
                    )
                    .order_by(
                        MonitorDatabaseCapacitySnapshot.db_name,
                        MonitorDatabaseCapacitySnapshot.collected_at,
                    )
                )
            )
            .scalars()
            .all()
        )
        first_by_db: dict[str, MonitorDatabaseCapacitySnapshot] = {}
        last_by_db: dict[str, MonitorDatabaseCapacitySnapshot] = {}
        for row in db_rows:
            first_by_db.setdefault(row.db_name, row)
            last_by_db[row.db_name] = row
        db_growth = [
            {
                "db_name": name,
                "first_size_bytes": first_by_db[name].total_size_bytes,
                "latest_size_bytes": last.total_size_bytes,
                "growth_bytes": last.total_size_bytes - first_by_db[name].total_size_bytes,
                "collected_at": last.collected_at.isoformat(),
            }
            for name, last in last_by_db.items()
        ]
        db_growth.sort(key=lambda item: item["growth_bytes"], reverse=True)
        table_total, tables = await MonitorService.get_table_capacity(db, instance_id, user, page_size=20)
        return {
            "top_databases": db_growth[:20],
            "top_tables": tables,
            "table_total": table_total,
            "days": days,
        }

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
                    await MonitorService.collect_instance_metrics(db, inst, cfg, collected_at=now)
                    collected += 1
                if capacity_due:
                    await MonitorService.collect_instance_capacity(db, inst, cfg, collected_at=now)
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
            await MonitorService.cleanup_old_snapshots(db, inst.id, cfg.retention_days, now)
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
        normalized = MonitorService._normalize_metric_payload(raw)
        MonitorService._apply_delta_rates(normalized, raw, previous, now)
        snapshot = MonitorMetricSnapshot(instance_id=inst.id, collected_at=now, **normalized)
        db.add(snapshot)
        await db.flush()
        await MonitorService.sync_alert_events_for_snapshot(db, inst, cfg, snapshot)
        cfg.last_metric_collect_at = now
        return snapshot

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
        current_connections = MonitorService._first_number(
            connections,
            "current",
            "connected_clients",
            "Threads_connected",
            "threads_connected",
            "current_connections",
        )
        max_connections = MonitorService._first_number(
            raw.get("variables") or raw,
            "max_connections",
            "Max_used_connections",
        ) or MonitorService._first_number(connections, "max_connections")
        usage = None
        if current_connections is not None and max_connections:
            usage = round(float(current_connections) / float(max_connections), 4)
        qps = MonitorService._first_number(
            stats, "qps", "instantaneous_ops_per_sec", "queries_per_second"
        )
        tps = MonitorService._first_number(stats, "tps", "transactions_per_second")
        return {
            "status": "failed" if raw.get("error") else "success",
            "error": str(raw.get("error") or ""),
            "missing_groups": missing,
            "is_up": bool(health.get("up")),
            "version": str(version or raw.get("server_version") or ""),
            "uptime_seconds": MonitorService._first_number(raw, "uptime_seconds", "uptime")
            or MonitorService._first_number(stats, "uptime_in_seconds"),
            "current_connections": current_connections,
            "active_sessions": MonitorService._first_number(
                raw.get("queries") or connections, "active_sessions", "active", "current"
            ),
            "max_connections": max_connections,
            "connection_usage": usage,
            "qps": float(qps) if qps is not None else None,
            "tps": float(tps) if tps is not None else None,
            "slow_queries": MonitorService._first_number(stats, "slow_queries", "Slow_queries"),
            "error_count": MonitorService._first_number(stats, "errors", "error_count"),
            "lock_waits": MonitorService._first_number(
                stats, "lock_waits", "Innodb_row_lock_waits"
            ),
            "long_transactions": MonitorService._first_number(stats, "long_transactions"),
            "replication_lag_seconds": MonitorService._first_number(
                raw.get("replication") or {}, "lag_seconds", "seconds_behind_master"
            ),
            "extra_metrics": MonitorService._json_safe(raw),
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
        qps = MonitorService._counter_rate(counters, previous_counters, seconds, "queries", "query_work")
        tps = MonitorService._counter_rate(
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
            current = MonitorService._coerce_float(counters.get(key))
            previous = MonitorService._coerce_float(previous_counters.get(key))
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

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    async def collect_instance_capacity(
        db: AsyncSession,
        inst: Instance,
        cfg: MonitorCollectConfig,
        collected_at: datetime | None = None,
    ) -> None:
        from app.engines.registry import get_engine

        now = collected_at or datetime.now(UTC)
        engine = get_engine(inst)
        db_names = await MonitorService._capacity_database_names(db, engine, inst)
        instance_total = 0
        for db_name in db_names:
            try:
                metas = await engine.get_tables_metas_data(db_name)
                table_rows = [
                    MonitorService._normalize_table_capacity(inst.id, db_name, meta, now)
                    for meta in metas
                ]
                db_total = sum(row.total_size_bytes for row in table_rows)
                db_data = sum(row.data_size_bytes for row in table_rows)
                db_index = sum(row.index_size_bytes for row in table_rows)
                db_row_count = sum(row.row_count for row in table_rows)
                instance_total += db_total
                for row in table_rows:
                    db.add(row)
                db.add(
                    MonitorDatabaseCapacitySnapshot(
                        instance_id=inst.id,
                        db_name=db_name,
                        collected_at=now,
                        table_count=len(table_rows),
                        data_size_bytes=db_data,
                        index_size_bytes=db_index,
                        total_size_bytes=db_total,
                        row_count=db_row_count,
                    )
                )
            except Exception as exc:
                db.add(
                    MonitorDatabaseCapacitySnapshot(
                        instance_id=inst.id,
                        db_name=db_name,
                        collected_at=now,
                        status="failed",
                        error=str(exc)[:4000],
                    )
                )
        latest = (
            await db.execute(
                select(MonitorMetricSnapshot)
                .where(MonitorMetricSnapshot.instance_id == inst.id)
                .order_by(MonitorMetricSnapshot.collected_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest:
            latest.total_size_bytes = instance_total
        cfg.last_capacity_collect_at = now

    @staticmethod
    async def _capacity_database_names(db: AsyncSession, engine: Any, inst: Instance) -> list[str]:
        registered = (
            (
                await db.execute(
                    select(InstanceDatabase.db_name)
                    .where(
                        InstanceDatabase.instance_id == inst.id,
                        InstanceDatabase.is_active.is_(True),
                    )
                    .order_by(InstanceDatabase.db_name)
                )
            )
            .scalars()
            .all()
        )
        if registered:
            return list(registered)
        rs = await engine.get_all_databases()
        if rs.error:
            raise AppException(rs.error, code=400)
        names = [
            str(
                row[0]
                if isinstance(row, (list, tuple))
                else next(iter(row.values()), "")
                if isinstance(row, dict)
                else row
            )
            for row in rs.rows
        ]
        return [name for name in names if name.lower() not in MonitorService.SYSTEM_DATABASES]

    @staticmethod
    def _normalize_table_capacity(
        instance_id: int,
        db_name: str,
        meta: dict[str, Any],
        collected_at: datetime,
    ) -> MonitorTableCapacitySnapshot:
        lowered = {str(k).lower(): v for k, v in meta.items()}
        table_name = str(
            lowered.get("table_name")
            or lowered.get("name")
            or lowered.get("collection")
            or lowered.get("tablename")
            or ""
        )
        data_size = MonitorService._int_value(
            lowered.get("data_length")
            or lowered.get("data_size")
            or lowered.get("data_bytes")
            or lowered.get("size")
            or 0
        )
        index_size = MonitorService._int_value(
            lowered.get("index_length") or lowered.get("index_size") or 0
        )
        total_size = MonitorService._int_value(
            lowered.get("total_size")
            or lowered.get("total_bytes")
            or lowered.get("bytes")
            or lowered.get("storage_size")
            or data_size + index_size
        )
        if not data_size and total_size and index_size:
            data_size = max(total_size - index_size, 0)
        row_count = MonitorService._int_value(
            lowered.get("table_rows")
            or lowered.get("rows")
            or lowered.get("count")
            or lowered.get("row_count")
            or 0
        )
        return MonitorTableCapacitySnapshot(
            instance_id=instance_id,
            db_name=db_name,
            table_name=table_name,
            collected_at=collected_at,
            data_size_bytes=data_size,
            index_size_bytes=index_size,
            total_size_bytes=total_size or data_size + index_size,
            row_count=row_count,
            extra=MonitorService._json_safe(meta),
        )

    @staticmethod
    def _int_value(value: Any) -> int:
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0

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
