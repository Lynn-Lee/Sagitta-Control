"""监控告警事件生命周期服务。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.models.instance import Instance
from app.models.monitor import MonitorAlertEvent, MonitorCollectConfig, MonitorMetricSnapshot
from app.models.user import ResourceGroup
from app.services.notify import NotifyService


class MonitorAlertService:
    """负责阈值告警规则评估、事件查询与处置闭环。"""

    @staticmethod
    def _can_access_instance(user: dict[str, Any], instance: Instance) -> bool:
        """观测域实例访问判定的统一入口：超管或持全局观测权限放行，否则要求用户与实例资源组有交集。"""
        if user.get("is_superuser") or "observability_instance_all" in user.get("permissions", []):
            return True
        user_rg_ids = set(user.get("resource_groups", []))
        instance_rg_ids = {rg.id for rg in instance.resource_groups}
        return bool(user_rg_ids & instance_rg_ids)

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def alert_rule_defaults() -> dict[str, dict[str, Any]]:
        return {
            "connection_usage": {"operator": ">=", "threshold": 0.8, "duration_count": 1},
            "replication_lag_seconds": {"operator": ">=", "threshold": 60, "duration_count": 1},
            "tablespace_used_pct": {"operator": ">=", "threshold": 85, "duration_count": 1},
            "fra_used_pct": {"operator": ">=", "threshold": 85, "duration_count": 1},
            "lock_waits": {"operator": ">", "threshold": 0, "duration_count": 1},
        }

    @staticmethod
    def metric_for_alert(snapshot: MonitorMetricSnapshot, rule_key: str) -> float | None:
        extra = snapshot.extra_metrics or {}
        if rule_key == "connection_usage":
            return float(snapshot.connection_usage) if snapshot.connection_usage is not None else None
        if rule_key == "replication_lag_seconds":
            return (
                float(snapshot.replication_lag_seconds)
                if snapshot.replication_lag_seconds is not None
                else None
            )
        if rule_key == "lock_waits":
            return float(snapshot.lock_waits or 0)
        if rule_key == "tablespace_used_pct":
            values = [
                MonitorAlertService._coerce_float(item.get("used_pct"))
                for item in (extra.get("tablespaces") or [])
                if isinstance(item, dict)
            ]
            present = [value for value in values if value is not None]
            return max(present) if present else None
        if rule_key == "fra_used_pct":
            return MonitorAlertService._coerce_float((extra.get("fra") or {}).get("used_pct"))
        return None

    @staticmethod
    def compare_alert_value(value: float, operator: str, threshold: float) -> bool:
        if operator == ">":
            return value > threshold
        if operator == "<":
            return value < threshold
        if operator == "<=":
            return value <= threshold
        if operator == "==":
            return value == threshold
        return value >= threshold

    @staticmethod
    def _enqueue_resolved_event(event: MonitorAlertEvent, inst: Instance, message: str) -> None:
        NotifyService.enqueue_event(
            {
                "event_type": "alert_resolved",
                "subject_type": "monitor_alert_event",
                "subject_id": event.id,
                "app_type": "监控告警",
                "title": f"{inst.instance_name} {event.rule_key} 已恢复",
                "instance_name": inst.instance_name,
                "risk_level": event.severity,
                "remark": message,
                "permissions": ["observability_alert_manage"],
                "detail_path": f"/monitor?instance_id={inst.id}&view=alerts",
            }
        )

    @staticmethod
    async def sync_alert_events_for_snapshot(
        db: AsyncSession,
        inst: Instance,
        cfg: MonitorCollectConfig,
        snapshot: MonitorMetricSnapshot,
    ) -> None:
        rules = {**MonitorAlertService.alert_rule_defaults(), **(cfg.alert_rules_override or {})}
        now = snapshot.collected_at or datetime.now(UTC)
        triggered: set[str] = set()
        for rule_key, rule in rules.items():
            if not isinstance(rule, dict) or rule.get("enabled") is False:
                continue
            value = MonitorAlertService.metric_for_alert(snapshot, rule_key)
            if value is None:
                continue
            threshold = float(rule.get("threshold", 0))
            operator = str(rule.get("operator") or ">=")
            if not MonitorAlertService.compare_alert_value(value, operator, threshold):
                continue
            triggered.add(rule_key)
            severity = "critical" if rule_key in {"tablespace_used_pct", "fra_used_pct"} and value >= 90 else "warning"
            title = f"{inst.instance_name} {rule_key} 告警"
            message = f"{rule_key} 当前值 {value}，触发条件 {operator} {threshold}"
            event = (
                await db.execute(
                    select(MonitorAlertEvent)
                    .where(
                        MonitorAlertEvent.instance_id == inst.id,
                        MonitorAlertEvent.rule_key == rule_key,
                        MonitorAlertEvent.status.in_(["firing", "acknowledged", "silenced"]),
                    )
                    .order_by(MonitorAlertEvent.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if event:
                event.last_seen_at = now
                event.metric_value = value
                event.threshold = threshold
                event.snapshot_id = snapshot.id
                event.message = message
                if event.status == "silenced" and event.silenced_until and event.silenced_until < now:
                    event.status = "firing"
            else:
                event = MonitorAlertEvent(
                    instance_id=inst.id,
                    rule_key=rule_key,
                    severity=severity,
                    status="firing",
                    title=title,
                    message=message,
                    metric_value=value,
                    threshold=threshold,
                    snapshot_id=snapshot.id,
                    first_seen_at=now,
                    last_seen_at=now,
                    extra={"db_type": inst.db_type},
                )
                db.add(event)
                await db.flush()
                NotifyService.enqueue_event(
                    {
                        "event_type": "alert_firing",
                        "subject_type": "monitor_alert_event",
                        "subject_id": event.id,
                        "app_type": "监控告警",
                        "title": title,
                        "instance_name": inst.instance_name,
                        "risk_level": severity,
                        "remark": message,
                        "permissions": ["observability_alert_manage"],
                        "detail_path": f"/monitor?instance_id={inst.id}&view=alerts",
                    }
                )

        active_events = (
            await db.execute(
                select(MonitorAlertEvent).where(
                    MonitorAlertEvent.instance_id == inst.id,
                    MonitorAlertEvent.status.in_(["firing", "acknowledged", "silenced"]),
                )
            )
        ).scalars().all()
        for event in active_events:
            if event.rule_key not in triggered:
                event.status = "resolved"
                event.resolved_at = now
                rule = rules.get(event.rule_key, {})
                if not isinstance(rule, dict) or rule.get("recover_notify") is not False:
                    MonitorAlertService._enqueue_resolved_event(
                        event,
                        inst,
                        f"{event.rule_key} 当前采样已低于触发条件，告警自动恢复",
                    )

    @staticmethod
    def alert_event_to_dict(event: MonitorAlertEvent, instance_name: str = "", db_type: str = "") -> dict[str, Any]:
        return {
            "id": event.id,
            "instance_id": event.instance_id,
            "instance_name": instance_name,
            "db_type": db_type,
            "rule_key": event.rule_key,
            "severity": event.severity,
            "status": event.status,
            "title": event.title,
            "message": event.message,
            "metric_value": event.metric_value,
            "threshold": event.threshold,
            "snapshot_id": event.snapshot_id,
            "first_seen_at": event.first_seen_at.isoformat() if event.first_seen_at else None,
            "last_seen_at": event.last_seen_at.isoformat() if event.last_seen_at else None,
            "resolved_at": event.resolved_at.isoformat() if event.resolved_at else None,
            "acknowledged_at": event.acknowledged_at.isoformat() if event.acknowledged_at else None,
            "acknowledged_by": event.acknowledged_by,
            "silenced_until": event.silenced_until.isoformat() if event.silenced_until else None,
            "closed_at": event.closed_at.isoformat() if event.closed_at else None,
            "closed_by": event.closed_by,
            "close_reason": event.close_reason,
            "extra": event.extra or {},
            "created_at": event.created_at.isoformat() if event.created_at else "",
        }

    @staticmethod
    async def list_alert_events(
        db: AsyncSession,
        user: dict[str, Any],
        status: str | None = None,
        instance_id: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[int, list[dict[str, Any]]]:
        query = select(MonitorAlertEvent, Instance).join(Instance, MonitorAlertEvent.instance_id == Instance.id)
        if instance_id:
            query = query.where(MonitorAlertEvent.instance_id == instance_id)
        if status:
            query = query.where(MonitorAlertEvent.status == status)
        if not (user.get("is_superuser") or "observability_instance_all" in user.get("permissions", [])):
            user_rg_ids = user.get("resource_groups", [])
            if not user_rg_ids:
                return 0, []
            query = (
                query.join(Instance.resource_groups.of_type(ResourceGroup))
                .where(ResourceGroup.id.in_(user_rg_ids))
                .distinct()
            )
        total = int((await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one())
        rows = (
            await db.execute(
                query.order_by(MonitorAlertEvent.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return (
            total,
            [
                MonitorAlertService.alert_event_to_dict(event, inst.instance_name, inst.db_type)
                for event, inst in rows
            ],
        )

    @staticmethod
    async def get_alert_event(db: AsyncSession, event_id: int, user: dict[str, Any]) -> dict[str, Any]:
        row = (
            await db.execute(
                select(MonitorAlertEvent, Instance)
                .join(Instance, MonitorAlertEvent.instance_id == Instance.id)
                .where(MonitorAlertEvent.id == event_id)
            )
        ).first()
        if not row:
            raise NotFoundException("告警事件不存在")
        event, inst = row
        if not MonitorAlertService._can_access_instance(user, inst):
            raise AppException("没有该实例的告警查看权限", code=403)
        return MonitorAlertService.alert_event_to_dict(event, inst.instance_name, inst.db_type)

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
        row = (
            await db.execute(
                select(MonitorAlertEvent, Instance)
                .join(Instance, MonitorAlertEvent.instance_id == Instance.id)
                .where(MonitorAlertEvent.id == event_id)
            )
        ).first()
        if not row:
            raise NotFoundException("告警事件不存在")
        event, inst = row
        if not MonitorAlertService._can_access_instance(user, inst):
            raise AppException("没有该实例的告警处理权限", code=403)
        now = datetime.now(UTC)
        operator = user.get("display_name") or user.get("username") or ""
        if action == "ack":
            event.status = "acknowledged"
            event.acknowledged_at = now
            event.acknowledged_by = operator
        elif action == "silence":
            event.status = "silenced"
            event.silenced_until = now + timedelta(minutes=max(1, minutes))
            event.acknowledged_by = operator
            event.acknowledged_at = event.acknowledged_at or now
        elif action == "resolve":
            event.status = "resolved"
            event.resolved_at = now
            event.acknowledged_by = event.acknowledged_by or operator
            event.acknowledged_at = event.acknowledged_at or now
            MonitorAlertService._enqueue_resolved_event(
                event,
                inst,
                f"{operator or '操作人'} 已确认指标恢复，告警转为已解决",
            )
        elif action == "close":
            event.status = "closed"
            event.closed_at = now
            event.closed_by = operator
            event.close_reason = reason[:500]
        else:
            raise AppException("不支持的告警操作", code=400)
        await db.commit()
        await db.refresh(event)
        return MonitorAlertService.alert_event_to_dict(event, inst.instance_name, inst.db_type)
