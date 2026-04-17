"""可观测中心 + Dashboard 统计服务（Sprint 5）。"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.models.instance import Instance
from app.models.monitor import MonitorCollectConfig, MonitorPrivilege, MonitorPrivilegeApply
from app.models.query import QueryLog, QueryPrivilegeApply
from app.models.role import UserGroup
from app.models.user import ResourceGroup, Users
from app.models.workflow import SqlWorkflow
from app.schemas.monitor import MonitorConfigCreate, MonitorConfigUpdate

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
    async def _resolve_query_scope(db: AsyncSession, user: dict) -> dict:
        if user.get("is_superuser") or user.get("role") == "dba":
            return {"mode": "global", "label": "全量数据", "user_ids": None, "instance_ids": None}

        if user.get("role") == "dba_group":
            user_rg_ids = user.get("resource_groups", [])
            if not user_rg_ids:
                return {"mode": "instance_scope", "label": "权限实例范围", "user_ids": None, "instance_ids": []}

            result = await db.execute(
                select(Instance.id)
                .join(Instance.resource_groups.of_type(ResourceGroup))
                .where(and_(Instance.is_active.is_(True), ResourceGroup.id.in_(user_rg_ids)))
                .distinct()
            )
            return {
                "mode": "instance_scope",
                "label": "权限实例范围",
                "user_ids": None,
                "instance_ids": list(result.scalars().all()),
            }

        leader_groups = await db.execute(
            select(UserGroup)
            .options(selectinload(UserGroup.members))
            .where(and_(UserGroup.leader_id == user["id"], UserGroup.is_active.is_(True)))
        )
        groups = leader_groups.scalars().all()
        if groups:
            user_ids = {user["id"]}
            for group in groups:
                user_ids.update(member.id for member in group.members if member.is_active)
            return {
                "mode": "group",
                "label": "组内数据",
                "user_ids": sorted(user_ids),
                "instance_ids": None,
            }

        return {"mode": "self", "label": "我的数据", "user_ids": [user["id"]], "instance_ids": None}

    @staticmethod
    def _apply_query_scope(stmt, scope: dict):
        if scope["mode"] in {"self", "group"}:
            user_ids = scope.get("user_ids") or []
            if not user_ids:
                return stmt.where(QueryLog.user_id == -1)
            return stmt.where(QueryLog.user_id.in_(user_ids))
        if scope["mode"] == "instance_scope":
            instance_ids = scope.get("instance_ids") or []
            if not instance_ids:
                return stmt.where(QueryLog.instance_id == -1)
            return stmt.where(QueryLog.instance_id.in_(instance_ids))
        return stmt

    @staticmethod
    def _apply_query_apply_scope(stmt, scope: dict):
        if scope["mode"] in {"self", "group"}:
            user_ids = scope.get("user_ids") or []
            if not user_ids:
                return stmt.where(QueryPrivilegeApply.user_id == -1)
            return stmt.where(QueryPrivilegeApply.user_id.in_(user_ids))
        if scope["mode"] == "instance_scope":
            instance_ids = scope.get("instance_ids") or []
            if not instance_ids:
                return stmt.where(QueryPrivilegeApply.instance_id == -1)
            return stmt.where(QueryPrivilegeApply.instance_id.in_(instance_ids))
        return stmt

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

        failure_count: list[int] = []
        masked_count: list[int] = []
        approved_count: list[int] = []
        rejected_count: list[int] = []
        pending_stock_count: list[int] = []
        for day_key in dates:
            failure_count.append(query_failure_map.get(day_key, 0) + rejected_map.get(day_key, 0))
            masked_count.append(masked_map.get(day_key, 0))
            approved_count.append(approved_map.get(day_key, 0))
            rejected_count.append(rejected_map.get(day_key, 0))
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
