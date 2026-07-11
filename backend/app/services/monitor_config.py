"""观测中心配置与权限域服务：采集配置 CRUD、监控权限申请/审批、统一采集配置编排。

从 `MonitorService` 拆出的叶子模块（配合 alerts / capacity / collect 叶子的门面委托
范式，见评估 #7）。实例访问判定 `_can_access_instance` 仍由 `MonitorAlertService`
持有（#8 收敛的 canonical），本模块横向复用，不反向依赖门面，无循环导入。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.models.instance import Instance
from app.models.monitor import (
    MonitorCollectConfig,
    MonitorPrivilege,
    MonitorPrivilegeApply,
)
from app.models.user import ResourceGroup, Users
from app.schemas.monitor import MonitorConfigCreate, MonitorConfigUpdate
from app.services.monitor_alerts import MonitorAlertService


class MonitorConfigService:
    """配置与权限域：采集配置 CRUD、SD targets、权限申请/审批、统一采集配置。"""

    # --- 采集配置 CRUD ---

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
        if not MonitorAlertService._can_access_instance(operator, instance):
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
        if not MonitorAlertService._can_access_instance(user, instance):
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
        if not MonitorAlertService._can_access_instance(user, instance):
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

    # --- 监控权限申请 / 审批 / 判定 ---

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
        if MonitorAlertService._can_access_instance(user, instance):
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

    # --- 原生 / 统一采集配置 ---

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
        if not MonitorAlertService._can_access_instance(user, instance):
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
        instances = await MonitorConfigService._accessible_instances(db, user)
        items = [
            await MonitorConfigService._unified_collect_config_item(db, instance, user)
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
        if not MonitorAlertService._can_access_instance(user, instance):
            raise AppException("不能配置资源组外实例的采集", code=403)

        await MonitorConfigService.upsert_native_config(db, instance_id, data.native, user)
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
        return await MonitorConfigService._unified_collect_config_item(db, instance, user)

    @staticmethod
    async def bulk_upsert_unified_collect_configs(
        db: AsyncSession,
        data: Any,
        user: dict,
    ) -> dict[str, Any]:
        instances = await MonitorConfigService._accessible_instances(db, user)
        success = 0
        failed: list[str] = []
        for instance in instances:
            try:
                await MonitorConfigService.upsert_unified_collect_config(db, instance.id, data, user)
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
