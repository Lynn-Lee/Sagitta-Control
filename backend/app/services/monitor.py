"""可观测中心 + Dashboard 统计服务（Sprint 5）。"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, case, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.models.archive import ArchiveJob, ArchiveJobStatus
from app.models.instance import Instance, InstanceDatabase
from app.models.monitor import MonitorCollectConfig, MonitorPrivilege, MonitorPrivilegeApply
from app.models.query import QueryLog, QueryPrivilege, QueryPrivilegeApply
from app.models.user import ResourceGroup, Users
from app.models.workflow import (
    SqlWorkflow,
    WorkflowAudit,
    WorkflowLog,
    WorkflowStatus,
    WorkflowType,
)
from app.schemas.monitor import MonitorConfigCreate, MonitorConfigUpdate
from app.services.audit import OP_CANCEL, OP_PASS, OP_REJECT, AuditService
from app.services.governance_scope import GovernanceScopeService

logger = logging.getLogger(__name__)


class MonitorService:

    @staticmethod
    def _can_access_instance(user: dict, instance: Instance) -> bool:
        if user.get("is_superuser") or "monitor_all_instances" in user.get("permissions", []):
            return True
        user_rg_ids = set(user.get("resource_groups", []))
        instance_rg_ids = {rg.id for rg in instance.resource_groups}
        return bool(user_rg_ids & instance_rg_ids)

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
        if not (user.get("is_superuser") or "monitor_all_instances" in user.get("permissions", [])):
            user_rg_ids = user.get("resource_groups", [])
            if not user_rg_ids:
                return 0, []
            from app.models.user import ResourceGroup

            query = query.join(Instance.resource_groups.of_type(ResourceGroup)).where(
                ResourceGroup.id.in_(user_rg_ids)
            ).distinct()

        total_q = await db.execute(select(func.count()).select_from(query.subquery()))
        total = total_q.scalar_one()
        result = await db.execute(
            query.offset((page - 1) * page_size).limit(page_size)
        )
        items = []
        for cfg, inst_name in result:
            items.append({
                "id": cfg.id, "instance_id": cfg.instance_id, "instance_name": inst_name,
                "is_enabled": cfg.is_enabled, "collect_interval": cfg.collect_interval,
                "exporter_url": cfg.exporter_url, "exporter_type": cfg.exporter_type,
                "alert_rules_override": cfg.alert_rules_override or {}, "created_by": cfg.created_by,
            })
        return total, items

    @staticmethod
    async def create_config(db: AsyncSession, data: MonitorConfigCreate, operator: dict) -> MonitorCollectConfig:
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
        existing = await db.execute(select(MonitorCollectConfig).where(MonitorCollectConfig.instance_id == data.instance_id))
        if existing.scalar_one_or_none():
            raise ConflictException(f"实例 ID={data.instance_id} 已有采集配置")
        cfg = MonitorCollectConfig(
            instance_id=data.instance_id, exporter_url=data.exporter_url,
            exporter_type=data.exporter_type, collect_interval=data.collect_interval,
            alert_rules_override=data.alert_rules_override, created_by=operator.get("username", ""),
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
            path_part = "/" + "/".join(url.split("//")[-1].split("/")[1:]) if "/" in url.split("//")[-1] else "/metrics"
            targets.append({
                "targets": [host_part],
                "labels": {
                    "__metrics_path__": path_part,
                    "__scrape_interval__": f"{cfg.collect_interval}s",
                    "job": cfg.exporter_type,
                    "instance_id": str(inst.id),
                    "instance_name": inst.instance_name,
                    "db_type": inst.db_type,
                },
            })
        return targets

    @staticmethod
    async def apply_privilege(db: AsyncSession, data, user: dict) -> MonitorPrivilegeApply:
        apply = MonitorPrivilegeApply(
            title=data.title, user_id=user["id"], instance_id=data.instance_id,
            group_id=data.group_id, valid_date=data.valid_date,
            apply_reason=data.apply_reason,
            audit_auth_groups=data.audit_auth_groups or str(data.group_id), status=0,
        )
        db.add(apply)
        await db.commit()
        await db.refresh(apply)
        return apply

    @staticmethod
    async def audit_privilege(db: AsyncSession, apply_id: int, action: str, operator: dict, remark: str = "") -> MonitorPrivilegeApply:
        result = await db.execute(select(MonitorPrivilegeApply).where(MonitorPrivilegeApply.id == apply_id))
        apply = result.scalar_one_or_none()
        if not apply:
            raise NotFoundException(f"申请 ID={apply_id} 不存在")
        if apply.status != 0:
            raise AppException("该申请已审批", code=400)
        if action == "pass":
            apply.status = 1
            db.add(MonitorPrivilege(apply_id=apply.id, user_id=apply.user_id, instance_id=apply.instance_id, valid_date=apply.valid_date, is_deleted=0))
        else:
            apply.status = 2
        await db.commit()
        await db.refresh(apply)
        return apply

    @staticmethod
    async def check_privilege(db: AsyncSession, user: dict, instance_id: int) -> bool:
        if user.get("is_superuser") or "monitor_all_instances" in user.get("permissions", []):
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
            select(MonitorPrivilege).where(and_(
                MonitorPrivilege.user_id == user["id"],
                MonitorPrivilege.instance_id == instance_id,
                MonitorPrivilege.valid_date >= date.today(),
                MonitorPrivilege.is_deleted == 0,
            ))
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def list_applies(db: AsyncSession, user: dict, status: int | None = None, page: int = 1, page_size: int = 20) -> tuple[int, list]:
        query = select(MonitorPrivilegeApply)
        if not user.get("is_superuser") and "monitor_review" not in user.get("permissions", []):
            query = query.where(MonitorPrivilegeApply.user_id == user["id"])
        if status is not None:
            query = query.where(MonitorPrivilegeApply.status == status)
        total_q = await db.execute(select(func.count()).select_from(query.subquery()))
        total = total_q.scalar_one()
        result = await db.execute(query.order_by(MonitorPrivilegeApply.created_at.desc()).offset((page-1)*page_size).limit(page_size))
        return total, list(result.scalars().all())


class DashboardService:
    @staticmethod
    async def _resolve_instance_scope(db: AsyncSession, user: dict) -> dict:
        if user.get("is_superuser") or user.get("role") in {"dba", "superadmin"}:
            return {"mode": "global", "label": "全量资源", "instance_ids": None}

        user_rg_ids = user.get("resource_groups", [])
        if not user_rg_ids:
            return {"mode": "instance_scope", "label": "可见资源范围", "instance_ids": []}

        result = await db.execute(
            select(Instance.id)
            .join(Instance.resource_groups.of_type(ResourceGroup))
            .where(and_(Instance.is_active.is_(True), ResourceGroup.id.in_(user_rg_ids)))
            .distinct()
        )
        return {
            "mode": "instance_scope",
            "label": "可见资源范围",
            "instance_ids": list(result.scalars().all()),
        }

    @staticmethod
    def _apply_instance_scope(stmt, scope: dict):
        if scope["mode"] == "instance_scope":
            instance_ids = scope.get("instance_ids") or []
            if not instance_ids:
                return stmt.where(Instance.id == -1)
            return stmt.where(Instance.id.in_(instance_ids))
        return stmt

    @staticmethod
    def _apply_instance_database_scope(stmt, scope: dict):
        if scope["mode"] == "instance_scope":
            instance_ids = scope.get("instance_ids") or []
            if not instance_ids:
                return stmt.where(InstanceDatabase.instance_id == -1)
            return stmt.where(InstanceDatabase.instance_id.in_(instance_ids))
        return stmt

    @staticmethod
    async def _resolve_query_scope(db: AsyncSession, user: dict) -> dict:
        return await GovernanceScopeService.resolve(db, user, "query")

    @staticmethod
    def _apply_query_scope(stmt, scope: dict):
        return GovernanceScopeService.apply_scope(
            stmt,
            scope,
            user_col=QueryLog.user_id,
            instance_col=QueryLog.instance_id,
        )

    @staticmethod
    def _apply_query_apply_scope(stmt, scope: dict):
        return GovernanceScopeService.apply_scope(
            stmt,
            scope,
            user_col=QueryPrivilegeApply.user_id,
            instance_col=QueryPrivilegeApply.instance_id,
        )

    @staticmethod
    def _apply_query_privilege_scope(stmt, scope: dict):
        return GovernanceScopeService.apply_scope(
            stmt,
            scope,
            user_col=QueryPrivilege.user_id,
            instance_col=QueryPrivilege.instance_id,
        )

    @staticmethod
    async def get_query_overview(db: AsyncSession, user: dict, days: int = 7) -> dict:
        now = datetime.now(UTC)
        period_start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        scope = await DashboardService._resolve_query_scope(db, user)

        async def scalar(stmt) -> int:
            return int((await db.execute(stmt)).scalar() or 0)

        period_query_stmt = DashboardService._apply_query_scope(
            select(QueryLog).where(QueryLog.created_at >= period_start),
            scope,
        )
        period_query_subq = period_query_stmt.subquery()
        period_query_count = await scalar(select(func.count()).select_from(period_query_subq))
        period_query_user_count = await scalar(select(func.count(distinct(period_query_subq.c.user_id))))

        period_masked_subq = DashboardService._apply_query_scope(
            select(QueryLog).where(
                and_(QueryLog.created_at >= period_start, QueryLog.masking.is_(True))
            ),
            scope,
        ).subquery()
        period_masked_count = await scalar(select(func.count()).select_from(period_masked_subq))

        query_failure_subq = DashboardService._apply_query_scope(
            select(QueryLog).where(
                and_(QueryLog.created_at >= period_start, QueryLog.priv_check.is_(False))
            ),
            scope,
        ).subquery()
        query_failure_count = await scalar(select(func.count()).select_from(query_failure_subq))

        apply_failure_subq = DashboardService._apply_query_apply_scope(
            select(QueryPrivilegeApply).where(
                and_(QueryPrivilegeApply.updated_at >= period_start, QueryPrivilegeApply.status == 2)
            ),
            scope,
        ).subquery()
        apply_failure_count = await scalar(select(func.count()).select_from(apply_failure_subq))

        approved_apply_subq = DashboardService._apply_query_apply_scope(
            select(QueryPrivilegeApply).where(
                and_(QueryPrivilegeApply.updated_at >= period_start, QueryPrivilegeApply.status == 1)
            ),
            scope,
        ).subquery()
        approved_query_priv_apply_count = await scalar(select(func.count()).select_from(approved_apply_subq))

        pending_apply_subq = DashboardService._apply_query_apply_scope(
            select(QueryPrivilegeApply).where(QueryPrivilegeApply.status == 0),
            scope,
        ).subquery()
        pending_query_priv_apply_count = await scalar(select(func.count()).select_from(pending_apply_subq))

        revoked_priv_subq = DashboardService._apply_query_privilege_scope(
            select(QueryPrivilege).where(
                and_(
                    QueryPrivilege.revoked_at >= period_start,
                    QueryPrivilege.is_deleted == 1,
                )
            ),
            scope,
        ).subquery()
        revoked_query_privilege_count = await scalar(select(func.count()).select_from(revoked_priv_subq))

        trend_stmt = DashboardService._apply_query_scope(
            select(
                func.date(QueryLog.created_at).label("d"),
                func.count().label("query_count"),
                func.count(distinct(QueryLog.user_id)).label("query_user_count"),
            ).where(QueryLog.created_at >= period_start),
            scope,
        ).group_by(func.date(QueryLog.created_at)).order_by(func.date(QueryLog.created_at))
        trend_rows = (await db.execute(trend_stmt)).all()
        trend_map = {
            str(row.d): {
                "query_count": int(row.query_count or 0),
                "query_user_count": int(row.query_user_count or 0),
            }
            for row in trend_rows
        }
        dates: list[str] = []
        query_count: list[int] = []
        query_user_count: list[int] = []
        for offset in range(days):
            day = period_start.date() + timedelta(days=offset)
            day_key = day.isoformat()
            dates.append(day_key)
            query_count.append(trend_map.get(day_key, {}).get("query_count", 0))
            query_user_count.append(trend_map.get(day_key, {}).get("query_user_count", 0))

        query_failure_stmt = DashboardService._apply_query_scope(
            select(
                func.date(QueryLog.created_at).label("d"),
                func.count().label("failure_count"),
            ).where(
                and_(QueryLog.created_at >= period_start, QueryLog.priv_check.is_(False))
            ),
            scope,
        ).group_by(func.date(QueryLog.created_at))
        query_failure_rows = (await db.execute(query_failure_stmt)).all()
        query_failure_map = {str(row.d): int(row.failure_count or 0) for row in query_failure_rows}

        masked_stmt = DashboardService._apply_query_scope(
            select(
                func.date(QueryLog.created_at).label("d"),
                func.count().label("masked_count"),
            ).where(
                and_(QueryLog.created_at >= period_start, QueryLog.masking.is_(True))
            ),
            scope,
        ).group_by(func.date(QueryLog.created_at))
        masked_rows = (await db.execute(masked_stmt)).all()
        masked_map = {str(row.d): int(row.masked_count or 0) for row in masked_rows}

        approved_stmt = DashboardService._apply_query_apply_scope(
            select(
                func.date(QueryPrivilegeApply.updated_at).label("d"),
                func.count().label("approved_count"),
            ).where(
                and_(QueryPrivilegeApply.updated_at >= period_start, QueryPrivilegeApply.status == 1)
            ),
            scope,
        ).group_by(func.date(QueryPrivilegeApply.updated_at))
        approved_rows = (await db.execute(approved_stmt)).all()
        approved_map = {str(row.d): int(row.approved_count or 0) for row in approved_rows}

        rejected_stmt = DashboardService._apply_query_apply_scope(
            select(
                func.date(QueryPrivilegeApply.updated_at).label("d"),
                func.count().label("rejected_count"),
            ).where(
                and_(QueryPrivilegeApply.updated_at >= period_start, QueryPrivilegeApply.status == 2)
            ),
            scope,
        ).group_by(func.date(QueryPrivilegeApply.updated_at))
        rejected_rows = (await db.execute(rejected_stmt)).all()
        rejected_map = {str(row.d): int(row.rejected_count or 0) for row in rejected_rows}

        revoked_stmt = DashboardService._apply_query_privilege_scope(
            select(
                func.date(QueryPrivilege.revoked_at).label("d"),
                func.count().label("revoked_count"),
            ).where(
                and_(
                    QueryPrivilege.revoked_at >= period_start,
                    QueryPrivilege.is_deleted == 1,
                )
            ),
            scope,
        ).group_by(func.date(QueryPrivilege.revoked_at))
        revoked_rows = (await db.execute(revoked_stmt)).all()
        revoked_map = {str(row.d): int(row.revoked_count or 0) for row in revoked_rows}

        failure_count: list[int] = []
        masked_count: list[int] = []
        approved_count: list[int] = []
        rejected_count: list[int] = []
        revoked_count: list[int] = []
        pending_stock_count: list[int] = []
        for day_key in dates:
            failure_count.append(query_failure_map.get(day_key, 0) + rejected_map.get(day_key, 0))
            masked_count.append(masked_map.get(day_key, 0))
            approved_count.append(approved_map.get(day_key, 0))
            rejected_count.append(rejected_map.get(day_key, 0))
            revoked_count.append(revoked_map.get(day_key, 0))
            day_end = datetime.fromisoformat(day_key).replace(tzinfo=UTC) + timedelta(days=1)
            pending_stock_stmt = DashboardService._apply_query_apply_scope(
                select(QueryPrivilegeApply).where(
                    and_(
                        QueryPrivilegeApply.created_at < day_end,
                        (
                            QueryPrivilegeApply.status == 0
                        ) | (
                            and_(
                                QueryPrivilegeApply.status.in_([1, 2]),
                                QueryPrivilegeApply.updated_at >= day_end,
                            )
                        ),
                    )
                ),
                scope,
            ).subquery()
            pending_stock_count.append(
                await scalar(select(func.count()).select_from(pending_stock_stmt))
            )

        top_stmt = DashboardService._apply_query_scope(
            select(
                QueryLog.user_id,
                func.count().label("query_count"),
            ).where(
                and_(QueryLog.created_at >= period_start, QueryLog.user_id.is_not(None))
            ),
            scope,
        ).group_by(QueryLog.user_id).order_by(func.count().desc()).limit(10)
        top_rows = (await db.execute(top_stmt)).all()
        top_user_ids = [row.user_id for row in top_rows if row.user_id is not None]
        display_name_map: dict[int, str] = {}
        if top_user_ids:
            user_rows = await db.execute(
                select(Users.id, Users.display_name, Users.username).where(Users.id.in_(top_user_ids))
            )
            for user_id, display_name, username in user_rows.all():
                display_name_map[user_id] = display_name or username

        return {
            "scope": {
                "mode": scope["mode"],
                "label": scope["label"],
            },
            "cards": {
                "period_query_count": period_query_count,
                "period_query_user_count": period_query_user_count,
                "period_failure_count": query_failure_count + apply_failure_count,
                "period_masked_count": period_masked_count,
                "pending_query_priv_apply_count": pending_query_priv_apply_count,
                "approved_query_priv_apply_count": approved_query_priv_apply_count,
                "rejected_query_priv_apply_count": apply_failure_count,
                "revoked_query_privilege_count": revoked_query_privilege_count,
            },
            "trend": {
                "range_label": f"最近{days}天",
                "dates": dates,
                "query_count": query_count,
                "query_user_count": query_user_count,
                "failure_count": failure_count,
                "masked_count": masked_count,
                "approved_count": approved_count,
                "rejected_count": rejected_count,
                "revoked_count": revoked_count,
                "pending_stock_count": pending_stock_count,
            },
            "top_users": [
                {
                    "display_name": display_name_map.get(row.user_id, f"用户{row.user_id}"),
                    "query_count": int(row.query_count or 0),
                }
                for row in top_rows
                if row.user_id is not None
            ],
        }

    @staticmethod
    async def get_instance_overview(db: AsyncSession, user: dict) -> dict:
        scope = await DashboardService._resolve_instance_scope(db, user)

        async def scalar(stmt) -> int:
            return int((await db.execute(stmt)).scalar() or 0)

        instance_stmt = DashboardService._apply_instance_scope(
            select(Instance).where(Instance.is_active.is_(True)),
            scope,
        )
        instance_subq = instance_stmt.subquery()
        visible_instance_count = await scalar(select(func.count()).select_from(instance_subq))

        db_stmt = DashboardService._apply_instance_database_scope(select(InstanceDatabase), scope)
        db_subq = db_stmt.subquery()
        synced_database_count = await scalar(select(func.count()).select_from(db_subq))

        enabled_db_subq = DashboardService._apply_instance_database_scope(
            select(InstanceDatabase).where(InstanceDatabase.is_active.is_(True)),
            scope,
        ).subquery()
        enabled_database_count = await scalar(select(func.count()).select_from(enabled_db_subq))

        disabled_db_subq = DashboardService._apply_instance_database_scope(
            select(InstanceDatabase).where(InstanceDatabase.is_active.is_(False)),
            scope,
        ).subquery()
        disabled_database_count = await scalar(select(func.count()).select_from(disabled_db_subq))

        type_stmt = DashboardService._apply_instance_scope(
            select(Instance.db_type, func.count().label("count")).where(Instance.is_active.is_(True)),
            scope,
        ).group_by(Instance.db_type).order_by(func.count().desc(), Instance.db_type)
        type_rows = (await db.execute(type_stmt)).all()

        active_instance_subq = DashboardService._apply_instance_scope(
            select(Instance).where(Instance.is_active.is_(True)),
            scope,
        ).subquery()
        enabled_instance_count = await scalar(select(func.count()).select_from(active_instance_subq))

        disabled_instance_subq = DashboardService._apply_instance_scope(
            select(Instance).where(Instance.is_active.is_(False)),
            scope,
        ).subquery()
        disabled_instance_count = await scalar(select(func.count()).select_from(disabled_instance_subq))

        status_items = [
            {"label": "已启用库/Schema", "count": enabled_database_count},
            {"label": "已禁用库/Schema", "count": disabled_database_count},
        ]

        instance_status_items = [
            {"label": "已启用实例", "count": enabled_instance_count},
            {"label": "已禁用实例", "count": disabled_instance_count},
        ]

        return {
            "scope": {
                "mode": scope["mode"],
                "label": scope["label"],
            },
            "cards": {
                "visible_instance_count": visible_instance_count,
                "synced_database_count": synced_database_count,
                "enabled_database_count": enabled_database_count,
                "disabled_database_count": disabled_database_count,
            },
            "instance_type_distribution": [
                {"db_type": row.db_type, "count": int(row.count or 0)}
                for row in type_rows
            ],
            "instance_status_distribution": instance_status_items,
            "database_status_distribution": status_items,
        }

    @staticmethod
    async def _resolve_workflow_scope(db: AsyncSession, user: dict) -> dict:
        return await GovernanceScopeService.resolve(db, user, "workflow")

    @staticmethod
    def _apply_workflow_scope(stmt, scope: dict):
        return GovernanceScopeService.apply_scope(
            stmt,
            scope,
            user_col=SqlWorkflow.engineer_id,
            instance_col=SqlWorkflow.instance_id,
        )

    @staticmethod
    def _apply_workflow_log_scope(stmt, scope: dict):
        return GovernanceScopeService.apply_scope(
            stmt,
            scope,
            user_col=SqlWorkflow.engineer_id,
            instance_col=SqlWorkflow.instance_id,
        )

    @staticmethod
    async def _visible_archive_workflow_ids_for_user(db: AsyncSession, user: dict) -> set[int]:
        pending_ids = await AuditService.get_pending_workflow_ids_for_user(db, user)
        audited_ids = await AuditService.get_audited_workflow_ids_for_user(db, user)
        return pending_ids | audited_ids

    @staticmethod
    async def _archive_conditions_for_user(db: AsyncSession, user: dict) -> list:
        if user.get("is_superuser") or "archive_review" in user.get("permissions", []) or "archive_execute" in user.get("permissions", []):
            return []
        visible_workflow_ids = await DashboardService._visible_archive_workflow_ids_for_user(db, user)
        visibility_conditions = [ArchiveJob.created_by_id == user.get("id")]
        if visible_workflow_ids:
            visibility_conditions.append(ArchiveJob.workflow_id.in_(visible_workflow_ids))
        return [or_(*visibility_conditions)]

    @staticmethod
    async def get_archive_overview(db: AsyncSession, user: dict, days: int = 7) -> dict:
        now = datetime.now(UTC)
        period_start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        conditions = await DashboardService._archive_conditions_for_user(db, user)

        async def scalar(stmt) -> int:
            return int((await db.execute(stmt)).scalar() or 0)

        def archive_stmt(*extra_conditions):
            stmt = select(ArchiveJob)
            all_conditions = [*conditions, *extra_conditions]
            if all_conditions:
                stmt = stmt.where(and_(*all_conditions))
            return stmt

        period_submit_subq = archive_stmt(ArchiveJob.created_at >= period_start).subquery()
        period_success_subq = archive_stmt(
            ArchiveJob.finished_at >= period_start,
            ArchiveJob.status == ArchiveJobStatus.SUCCESS,
        ).subquery()
        period_failed_subq = archive_stmt(
            ArchiveJob.finished_at >= period_start,
            ArchiveJob.status == ArchiveJobStatus.FAILED,
        ).subquery()
        period_canceled_subq = archive_stmt(
            ArchiveJob.finished_at >= period_start,
            ArchiveJob.status == ArchiveJobStatus.CANCELED,
        ).subquery()

        period_submit_count = await scalar(select(func.count()).select_from(period_submit_subq))
        success_count = await scalar(select(func.count()).select_from(period_success_subq))
        failed_count = await scalar(select(func.count()).select_from(period_failed_subq))
        canceled_count = await scalar(select(func.count()).select_from(period_canceled_subq))

        pending_count = await scalar(select(func.count()).select_from(archive_stmt(ArchiveJob.status == ArchiveJobStatus.PENDING_REVIEW).subquery()))
        approved_count = await scalar(select(func.count()).select_from(archive_stmt(ArchiveJob.status == ArchiveJobStatus.APPROVED).subquery()))
        scheduled_count = await scalar(select(func.count()).select_from(archive_stmt(ArchiveJob.status == ArchiveJobStatus.SCHEDULED).subquery()))
        running_count = await scalar(select(func.count()).select_from(archive_stmt(ArchiveJob.status.in_((ArchiveJobStatus.QUEUED, ArchiveJobStatus.RUNNING))).subquery()))
        paused_count = await scalar(select(func.count()).select_from(archive_stmt(ArchiveJob.status.in_((ArchiveJobStatus.PAUSING, ArchiveJobStatus.PAUSED))).subquery()))
        high_risk_active_count = await scalar(select(func.count()).select_from(archive_stmt(
            ArchiveJob.risk_level == "high",
            ArchiveJob.status.in_(
                (
                    ArchiveJobStatus.PENDING_REVIEW,
                    ArchiveJobStatus.APPROVED,
                    ArchiveJobStatus.SCHEDULED,
                    ArchiveJobStatus.QUEUED,
                    ArchiveJobStatus.RUNNING,
                    ArchiveJobStatus.PAUSING,
                    ArchiveJobStatus.PAUSED,
                )
            ),
        ).subquery()))

        row_totals = (await db.execute(
            archive_stmt(ArchiveJob.created_at >= period_start).with_only_columns(
                func.coalesce(func.sum(ArchiveJob.estimated_rows), 0),
                func.coalesce(func.sum(ArchiveJob.processed_rows), 0),
            )
        )).one()

        submit_trend_rows = (await db.execute(
            archive_stmt(ArchiveJob.created_at >= period_start).with_only_columns(
                func.date(ArchiveJob.created_at).label("d"),
                func.count().label("submit_count"),
                func.coalesce(func.sum(ArchiveJob.estimated_rows), 0).label("estimated_rows"),
            ).group_by(func.date(ArchiveJob.created_at)).order_by(func.date(ArchiveJob.created_at))
        )).all()
        submit_trend_map = {
            str(row.d): {
                "submit_count": int(row.submit_count or 0),
                "estimated_rows": int(row.estimated_rows or 0),
            }
            for row in submit_trend_rows
        }

        finished_trend_rows = (await db.execute(
            archive_stmt(
                ArchiveJob.finished_at >= period_start,
                ArchiveJob.status.in_((ArchiveJobStatus.SUCCESS, ArchiveJobStatus.FAILED, ArchiveJobStatus.CANCELED)),
            ).with_only_columns(
                func.date(ArchiveJob.finished_at).label("d"),
                func.sum(case((ArchiveJob.status == ArchiveJobStatus.SUCCESS, 1), else_=0)).label("success_count"),
                func.sum(case((ArchiveJob.status == ArchiveJobStatus.FAILED, 1), else_=0)).label("failed_count"),
                func.sum(case((ArchiveJob.status == ArchiveJobStatus.CANCELED, 1), else_=0)).label("canceled_count"),
                func.coalesce(func.sum(ArchiveJob.processed_rows), 0).label("processed_rows"),
            ).group_by(func.date(ArchiveJob.finished_at)).order_by(func.date(ArchiveJob.finished_at))
        )).all()
        finished_trend_map = {
            str(row.d): {
                "success_count": int(row.success_count or 0),
                "failed_count": int(row.failed_count or 0),
                "canceled_count": int(row.canceled_count or 0),
                "processed_rows": int(row.processed_rows or 0),
            }
            for row in finished_trend_rows
        }

        dates: list[str] = []
        submit_count: list[int] = []
        success_trend_count: list[int] = []
        failed_trend_count: list[int] = []
        canceled_trend_count: list[int] = []
        estimated_rows_trend: list[int] = []
        processed_rows_trend: list[int] = []
        active_stock_count: list[int] = []
        for offset in range(days):
            day = period_start.date() + timedelta(days=offset)
            day_key = day.isoformat()
            day_end = datetime.fromisoformat(day_key).replace(tzinfo=UTC) + timedelta(days=1)
            dates.append(day_key)
            submit_day = submit_trend_map.get(day_key, {})
            finished_day = finished_trend_map.get(day_key, {})
            submit_count.append(submit_day.get("submit_count", 0))
            estimated_rows_trend.append(submit_day.get("estimated_rows", 0))
            success_trend_count.append(finished_day.get("success_count", 0))
            failed_trend_count.append(finished_day.get("failed_count", 0))
            canceled_trend_count.append(finished_day.get("canceled_count", 0))
            processed_rows_trend.append(finished_day.get("processed_rows", 0))
            active_stock_stmt = archive_stmt(
                ArchiveJob.created_at < day_end,
                ArchiveJob.status.in_(
                    (
                        ArchiveJobStatus.PENDING_REVIEW,
                        ArchiveJobStatus.APPROVED,
                        ArchiveJobStatus.SCHEDULED,
                        ArchiveJobStatus.QUEUED,
                        ArchiveJobStatus.RUNNING,
                        ArchiveJobStatus.PAUSING,
                        ArchiveJobStatus.PAUSED,
                    )
                ),
            ).subquery()
            active_stock_count.append(await scalar(select(func.count()).select_from(active_stock_stmt)))

        top_submitter_rows = (await db.execute(
            archive_stmt(ArchiveJob.created_at >= period_start).with_only_columns(
                ArchiveJob.created_by_id,
                func.count().label("count"),
                func.coalesce(func.sum(ArchiveJob.estimated_rows), 0).label("estimated_rows"),
            ).group_by(ArchiveJob.created_by_id).order_by(func.count().desc()).limit(10)
        )).all()
        submitter_ids = [row.created_by_id for row in top_submitter_rows if row.created_by_id is not None]
        user_map: dict[int, str] = {}
        if submitter_ids:
            user_rows = await db.execute(select(Users.id, Users.display_name, Users.username).where(Users.id.in_(submitter_ids)))
            user_map = {user_id: (display_name or username) for user_id, display_name, username in user_rows.all()}

        top_instance_rows = (await db.execute(
            archive_stmt(ArchiveJob.created_at >= period_start)
            .join(Instance, ArchiveJob.source_instance_id == Instance.id)
            .with_only_columns(
                Instance.instance_name,
                func.count().label("count"),
                func.coalesce(func.sum(ArchiveJob.estimated_rows), 0).label("estimated_rows"),
            )
            .group_by(Instance.instance_name)
            .order_by(func.count().desc())
            .limit(10)
        )).all()

        top_table_rows = (await db.execute(
            archive_stmt(ArchiveJob.created_at >= period_start).with_only_columns(
                ArchiveJob.source_db,
                ArchiveJob.source_table,
                func.count().label("count"),
                func.coalesce(func.sum(ArchiveJob.estimated_rows), 0).label("estimated_rows"),
                func.coalesce(func.sum(ArchiveJob.processed_rows), 0).label("processed_rows"),
            ).group_by(ArchiveJob.source_db, ArchiveJob.source_table).order_by(func.sum(ArchiveJob.estimated_rows).desc()).limit(10)
        )).all()

        return {
            "scope": {
                "mode": "archive",
                "label": "归档任务可见范围",
            },
            "cards": {
                "period_submit_count": period_submit_count,
                "pending_count": pending_count,
                "approved_count": approved_count,
                "scheduled_count": scheduled_count,
                "running_count": running_count,
                "paused_count": paused_count,
                "success_count": success_count,
                "failed_count": failed_count,
                "canceled_count": canceled_count,
                "estimated_rows": int(row_totals[0] or 0),
                "processed_rows": int(row_totals[1] or 0),
                "high_risk_active_count": high_risk_active_count,
            },
            "trend": {
                "dates": dates,
                "submit_count": submit_count,
                "success_count": success_trend_count,
                "failed_count": failed_trend_count,
                "canceled_count": canceled_trend_count,
                "estimated_rows": estimated_rows_trend,
                "processed_rows": processed_rows_trend,
                "active_stock_count": active_stock_count,
            },
            "top_submitters": [
                {
                    "display_name": user_map.get(row.created_by_id, f"用户{row.created_by_id}"),
                    "count": int(row.count or 0),
                    "estimated_rows": int(row.estimated_rows or 0),
                }
                for row in top_submitter_rows if row.created_by_id is not None
            ],
            "top_instances": [
                {
                    "instance_name": row.instance_name or "未知实例",
                    "count": int(row.count or 0),
                    "estimated_rows": int(row.estimated_rows or 0),
                }
                for row in top_instance_rows
            ],
            "top_tables": [
                {
                    "source_label": f"{row.source_db or '未知库'}.{row.source_table or '未知表'}",
                    "count": int(row.count or 0),
                    "estimated_rows": int(row.estimated_rows or 0),
                    "processed_rows": int(row.processed_rows or 0),
                }
                for row in top_table_rows
            ],
        }

    @staticmethod
    async def get_workflow_overview(db: AsyncSession, user: dict, days: int = 7) -> dict:
        now = datetime.now(UTC)
        period_start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        scope = await DashboardService._resolve_workflow_scope(db, user)

        async def scalar(stmt) -> int:
            return int((await db.execute(stmt)).scalar() or 0)

        def workflow_stmt(*conditions):
            stmt = select(SqlWorkflow)
            stmt = DashboardService._apply_workflow_scope(stmt, scope)
            stmt = stmt.where(
                SqlWorkflow.id.in_(
                    select(WorkflowAudit.workflow_id).where(WorkflowAudit.workflow_type == int(WorkflowType.SQL))
                )
            )
            if conditions:
                stmt = stmt.where(and_(*conditions))
            return stmt

        def workflow_log_stmt(*conditions):
            stmt = (
                select(WorkflowLog, SqlWorkflow)
                .join(WorkflowAudit, WorkflowLog.audit_id == WorkflowAudit.id)
                .join(SqlWorkflow, WorkflowAudit.workflow_id == SqlWorkflow.id)
                .where(WorkflowAudit.workflow_type == int(WorkflowType.SQL))
            )
            stmt = DashboardService._apply_workflow_log_scope(stmt, scope)
            if conditions:
                stmt = stmt.where(and_(*conditions))
            return stmt

        period_submit_subq = workflow_stmt(SqlWorkflow.created_at >= period_start).subquery()
        today_submit_count = await scalar(select(func.count()).select_from(period_submit_subq))

        period_approved_subq = workflow_log_stmt(
            WorkflowLog.created_at >= period_start,
            WorkflowLog.operation_type == OP_PASS,
            WorkflowLog.remark.like("全部审批通过%"),
        ).with_only_columns(
            SqlWorkflow.id.label("workflow_id"),
            WorkflowLog.created_at.label("created_at"),
        ).subquery()
        today_approved_count = await scalar(select(func.count(distinct(period_approved_subq.c.workflow_id))).select_from(period_approved_subq))

        period_rejected_subq = workflow_log_stmt(
            WorkflowLog.created_at >= period_start,
            WorkflowLog.operation_type == OP_REJECT,
        ).with_only_columns(
            SqlWorkflow.id.label("workflow_id"),
            WorkflowLog.created_at.label("created_at"),
        ).subquery()
        today_rejected_count = await scalar(select(func.count(distinct(period_rejected_subq.c.workflow_id))).select_from(period_rejected_subq))

        pending_subq = workflow_stmt(SqlWorkflow.status == WorkflowStatus.PENDING_REVIEW).subquery()
        pending_count = await scalar(select(func.count()).select_from(pending_subq))

        queued_subq = workflow_stmt(SqlWorkflow.status == WorkflowStatus.QUEUING).subquery()
        queued_count = await scalar(select(func.count()).select_from(queued_subq))

        running_subq = workflow_stmt(SqlWorkflow.status == WorkflowStatus.EXECUTING).subquery()
        running_count = await scalar(select(func.count()).select_from(running_subq))

        execute_success_subq = workflow_stmt(
            SqlWorkflow.finish_time >= period_start,
            SqlWorkflow.status == WorkflowStatus.FINISH,
        ).subquery()
        today_execute_success_count = await scalar(select(func.count()).select_from(execute_success_subq))

        execute_failed_subq = workflow_stmt(
            SqlWorkflow.finish_time >= period_start,
            SqlWorkflow.status == WorkflowStatus.EXCEPTION,
        ).subquery()
        today_execute_failed_count = await scalar(select(func.count()).select_from(execute_failed_subq))

        cancel_subq = workflow_log_stmt(
            WorkflowLog.created_at >= period_start,
            WorkflowLog.operation_type == OP_CANCEL,
        ).with_only_columns(
            SqlWorkflow.id.label("workflow_id"),
            WorkflowLog.created_at.label("created_at"),
        ).subquery()
        today_cancel_count = await scalar(select(func.count(distinct(cancel_subq.c.workflow_id))).select_from(cancel_subq))

        finished_ids: set[int] = set()
        for subq in (execute_success_subq, execute_failed_subq):
            ids = await db.execute(select(distinct(subq.c.id)))
            finished_ids.update(ids.scalars().all())
        for subq in (cancel_subq, period_rejected_subq):
            ids = await db.execute(select(distinct(subq.c.workflow_id)))
            finished_ids.update(ids.scalars().all())
        today_finished_count = len(finished_ids)

        submit_trend_stmt = workflow_stmt(
            SqlWorkflow.created_at >= period_start,
        ).with_only_columns(
            func.date(SqlWorkflow.created_at).label("d"),
            func.count().label("submit_count"),
        ).group_by(func.date(SqlWorkflow.created_at)).order_by(func.date(SqlWorkflow.created_at))
        submit_trend_rows = (await db.execute(submit_trend_stmt)).all()
        submit_trend_map = {str(row.d): int(row.submit_count or 0) for row in submit_trend_rows}

        approved_trend_stmt = workflow_log_stmt(
            WorkflowLog.created_at >= period_start,
            WorkflowLog.operation_type == OP_PASS,
            WorkflowLog.remark.like("全部审批通过%"),
        ).with_only_columns(
            func.date(WorkflowLog.created_at).label("d"),
            func.count(distinct(SqlWorkflow.id)).label("approved_count"),
        ).group_by(func.date(WorkflowLog.created_at))
        approved_trend_rows = (await db.execute(approved_trend_stmt)).all()
        approved_trend_map = {str(row.d): int(row.approved_count or 0) for row in approved_trend_rows}

        rejected_trend_stmt = workflow_log_stmt(
            WorkflowLog.created_at >= period_start,
            WorkflowLog.operation_type == OP_REJECT,
        ).with_only_columns(
            func.date(WorkflowLog.created_at).label("d"),
            func.count(distinct(SqlWorkflow.id)).label("rejected_count"),
        ).group_by(func.date(WorkflowLog.created_at))
        rejected_trend_rows = (await db.execute(rejected_trend_stmt)).all()
        rejected_trend_map = {str(row.d): int(row.rejected_count or 0) for row in rejected_trend_rows}

        cancel_trend_stmt = workflow_log_stmt(
            WorkflowLog.created_at >= period_start,
            WorkflowLog.operation_type == OP_CANCEL,
        ).with_only_columns(
            func.date(WorkflowLog.created_at).label("d"),
            func.count(distinct(SqlWorkflow.id)).label("cancel_count"),
        ).group_by(func.date(WorkflowLog.created_at))
        cancel_trend_rows = (await db.execute(cancel_trend_stmt)).all()
        cancel_trend_map = {str(row.d): int(row.cancel_count or 0) for row in cancel_trend_rows}

        execute_success_trend_stmt = workflow_stmt(
            SqlWorkflow.finish_time >= period_start,
            SqlWorkflow.status == WorkflowStatus.FINISH,
        ).with_only_columns(
            func.date(SqlWorkflow.finish_time).label("d"),
            func.count().label("success_count"),
        ).group_by(func.date(SqlWorkflow.finish_time))
        execute_success_trend_rows = (await db.execute(execute_success_trend_stmt)).all()
        execute_success_trend_map = {str(row.d): int(row.success_count or 0) for row in execute_success_trend_rows}

        execute_failed_trend_stmt = workflow_stmt(
            SqlWorkflow.finish_time >= period_start,
            SqlWorkflow.status == WorkflowStatus.EXCEPTION,
        ).with_only_columns(
            func.date(SqlWorkflow.finish_time).label("d"),
            func.count().label("failed_count"),
        ).group_by(func.date(SqlWorkflow.finish_time))
        execute_failed_trend_rows = (await db.execute(execute_failed_trend_stmt)).all()
        execute_failed_trend_map = {str(row.d): int(row.failed_count or 0) for row in execute_failed_trend_rows}

        dates: list[str] = []
        submit_count: list[int] = []
        approved_count: list[int] = []
        rejected_count: list[int] = []
        cancel_count: list[int] = []
        execute_failed_count: list[int] = []
        queued_stock_count: list[int] = []
        running_stock_count: list[int] = []
        execute_success_count: list[int] = []
        pending_stock_count: list[int] = []

        for offset in range(days):
            day = period_start.date() + timedelta(days=offset)
            day_key = day.isoformat()
            day_end = datetime.fromisoformat(day_key).replace(tzinfo=UTC) + timedelta(days=1)
            dates.append(day_key)
            submit_count.append(submit_trend_map.get(day_key, 0))
            approved_count.append(approved_trend_map.get(day_key, 0))
            rejected_count.append(rejected_trend_map.get(day_key, 0))
            cancel_count.append(cancel_trend_map.get(day_key, 0))
            execute_failed_count.append(execute_failed_trend_map.get(day_key, 0))
            execute_success_count.append(execute_success_trend_map.get(day_key, 0))

            pending_stock_stmt = workflow_stmt(
                SqlWorkflow.created_at < day_end,
                or_(
                    SqlWorkflow.status == WorkflowStatus.PENDING_REVIEW,
                    and_(
                        SqlWorkflow.status != WorkflowStatus.PENDING_REVIEW,
                        SqlWorkflow.updated_at >= day_end,
                    ),
                ),
            ).subquery()
            pending_stock_count.append(await scalar(select(func.count()).select_from(pending_stock_stmt)))

            queued_stock_stmt = workflow_stmt(
                SqlWorkflow.status == WorkflowStatus.QUEUING,
                SqlWorkflow.created_at < day_end,
            ).subquery()
            queued_stock_count.append(await scalar(select(func.count()).select_from(queued_stock_stmt)))

            running_stock_stmt = workflow_stmt(
                SqlWorkflow.status == WorkflowStatus.EXECUTING,
                SqlWorkflow.created_at < day_end,
            ).subquery()
            running_stock_count.append(await scalar(select(func.count()).select_from(running_stock_stmt)))

        top_submitter_stmt = workflow_stmt(
            SqlWorkflow.created_at >= period_start,
        ).with_only_columns(
            SqlWorkflow.engineer_id,
            func.count().label("count"),
        ).group_by(SqlWorkflow.engineer_id).order_by(func.count().desc()).limit(10)
        top_submitter_rows = (await db.execute(top_submitter_stmt)).all()
        submitter_ids = [row.engineer_id for row in top_submitter_rows if row.engineer_id is not None]
        user_map: dict[int, str] = {}
        if submitter_ids:
            user_rows = await db.execute(
                select(Users.id, Users.display_name, Users.username).where(Users.id.in_(submitter_ids))
            )
            user_map = {user_id: (display_name or username) for user_id, display_name, username in user_rows.all()}

        top_instance_stmt = workflow_stmt(
            SqlWorkflow.created_at >= period_start,
        ).join(Instance, SqlWorkflow.instance_id == Instance.id).with_only_columns(
            Instance.instance_name,
            func.count().label("count"),
        ).group_by(Instance.instance_name).order_by(func.count().desc()).limit(10)
        top_instance_rows = (await db.execute(top_instance_stmt)).all()

        top_database_stmt = workflow_stmt(
            SqlWorkflow.created_at >= period_start,
        ).with_only_columns(
            SqlWorkflow.db_name,
            func.count().label("count"),
        ).group_by(SqlWorkflow.db_name).order_by(func.count().desc()).limit(10)
        top_database_rows = (await db.execute(top_database_stmt)).all()

        top_approver_stmt = workflow_log_stmt(
            WorkflowLog.created_at >= period_start,
            WorkflowLog.operation_type.in_((OP_PASS, OP_REJECT)),
        ).with_only_columns(
            WorkflowLog.operator_id,
            func.count().label("count"),
        ).group_by(WorkflowLog.operator_id).order_by(func.count().desc()).limit(10)
        top_approver_rows = (await db.execute(top_approver_stmt)).all()
        approver_ids = [row.operator_id for row in top_approver_rows if row.operator_id is not None]
        if approver_ids:
            approver_rows = await db.execute(
                select(Users.id, Users.display_name, Users.username).where(Users.id.in_(approver_ids))
            )
            for user_id, display_name, username in approver_rows.all():
                user_map[user_id] = display_name or username

        top_execute_instance_stmt = workflow_stmt(
            SqlWorkflow.finish_time >= period_start,
            SqlWorkflow.status.in_((WorkflowStatus.FINISH, WorkflowStatus.EXCEPTION)),
        ).join(Instance, SqlWorkflow.instance_id == Instance.id).with_only_columns(
            Instance.instance_name,
            func.count().label("count"),
        ).group_by(Instance.instance_name).order_by(func.count().desc()).limit(10)
        top_execute_instance_rows = (await db.execute(top_execute_instance_stmt)).all()

        return {
            "scope": {
                "mode": scope["mode"],
                "label": scope["label"],
            },
            "cards": {
                "today_submit_count": today_submit_count,
                "today_approved_count": today_approved_count,
                "today_rejected_count": today_rejected_count,
                "pending_count": pending_count,
                "queued_count": queued_count,
                "running_count": running_count,
                "today_execute_success_count": today_execute_success_count,
                "today_execute_failed_count": today_execute_failed_count,
                "today_cancel_count": today_cancel_count,
                "today_finished_count": today_finished_count,
            },
            "submit_trend": {
                "dates": dates,
                "submit_count": submit_count,
                "approved_count": approved_count,
            },
            "governance_trend": {
                "dates": dates,
                "rejected_count": rejected_count,
                "cancel_count": cancel_count,
                "execute_failed_count": execute_failed_count,
            },
            "execute_trend": {
                "dates": dates,
                "queued_count": queued_stock_count,
                "running_count": running_stock_count,
                "success_count": execute_success_count,
            },
            "pending_stock_trend": {
                "dates": dates,
                "pending_count": pending_stock_count,
            },
            "top_submitters": [
                {"display_name": user_map.get(row.engineer_id, f"用户{row.engineer_id}"), "count": int(row.count or 0)}
                for row in top_submitter_rows if row.engineer_id is not None
            ],
            "top_instances": [
                {"instance_name": row.instance_name or "未知实例", "count": int(row.count or 0)}
                for row in top_instance_rows
            ],
            "top_databases": [
                {"db_name": row.db_name or "未知数据库", "count": int(row.count or 0)}
                for row in top_database_rows
            ],
            "top_approvers": [
                {"display_name": user_map.get(row.operator_id, f"用户{row.operator_id}"), "count": int(row.count or 0)}
                for row in top_approver_rows if row.operator_id is not None
            ],
            "top_execute_instances": [
                {"instance_name": row.instance_name or "未知实例", "count": int(row.count or 0)}
                for row in top_execute_instance_rows
            ],
        }

    @staticmethod
    async def get_stats(db: AsyncSession, days: int = 30) -> dict:
        """
        Dashboard 统计。
        days: 统计周期（天），默认 30 天，前端可自定义传入。
        返回：指定周期内各状态工单数量 + 全局统计。
        """
        now = datetime.now(UTC)
        period_start = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        async def count(stmt):
            return (await db.execute(stmt)).scalar_one()

        # 指定周期内各状态工单数量
        async def wf_count_by_status(status: int) -> int:
            return await count(
                select(func.count()).select_from(SqlWorkflow).where(
                    and_(SqlWorkflow.created_at >= period_start, SqlWorkflow.status == status)
                )
            )

        # 周期内总提交数
        wf_total = await count(
            select(func.count()).select_from(SqlWorkflow)
            .where(SqlWorkflow.created_at >= period_start)
        )

        return {
            "period_days": days,
            "workflow_total": wf_total,
            # 各状态明细
            "workflow_by_status": {
                "pending_review":   await wf_count_by_status(0),   # 待审核
                "review_rejected":  await wf_count_by_status(1),   # 审批驳回
                "review_pass":      await wf_count_by_status(2),   # 审核通过
                "timing":           await wf_count_by_status(3),   # 定时执行
                "queuing":          await wf_count_by_status(4),   # 队列中
                "executing":        await wf_count_by_status(5),   # 执行中
                "finish":           await wf_count_by_status(6),   # 执行成功
                "exception":        await wf_count_by_status(7),   # 执行异常
                "canceled":         await wf_count_by_status(8),   # 已取消
            },
            # 全局统计（不受周期限制）
            "instance_total": await count(
                select(func.count()).select_from(Instance).where(Instance.is_active)
            ),
            "query_today_total": await count(
                select(func.count()).select_from(QueryLog).where(QueryLog.created_at >= today_start)
            ),
            "monitor_instance_total": await count(
                select(func.count()).select_from(MonitorCollectConfig)
                .where(MonitorCollectConfig.is_enabled)
            ),
        }

    @staticmethod
    async def get_workflow_trend(db: AsyncSession, days: int = 7) -> list[dict]:
        """
        工单趋势。days 由前端传入，支持用户自定义周期。
        返回每天各状态工单数量。
        """
        result = []
        now = datetime.now(UTC)
        for i in range(days - 1, -1, -1):
            day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)

            async def day_count_status(status_val: int, ds=day_start, de=day_end) -> int:
                stmt = select(func.count()).select_from(SqlWorkflow).where(
                    and_(SqlWorkflow.created_at >= ds, SqlWorkflow.created_at < de,
                         SqlWorkflow.status == status_val)
                )
                return (await db.execute(stmt)).scalar_one()

            async def day_count_all(ds=day_start, de=day_end) -> int:
                stmt = select(func.count()).select_from(SqlWorkflow).where(
                    and_(SqlWorkflow.created_at >= ds, SqlWorkflow.created_at < de)
                )
                return (await db.execute(stmt)).scalar_one()

            result.append({
                "date": day_start.strftime("%m-%d"),
                "submit":   await day_count_all(),
                "finish":   await day_count_status(6),
                "reject":   await day_count_status(1),
                "canceled": await day_count_status(8),
                "exception":await day_count_status(7),
            })
        return result

    @staticmethod
    async def get_instance_dist(db: AsyncSession) -> list[dict]:
        result = await db.execute(
            select(Instance.db_type, func.count().label("count"))
            .where(Instance.is_active)
            .group_by(Instance.db_type)
            .order_by(func.count().desc())
        )
        return [{"db_type": row.db_type, "count": row.count} for row in result]
