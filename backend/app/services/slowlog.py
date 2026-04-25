"""Slow query analysis service."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, NotFoundException
from app.engines.models import ResultSet
from app.engines.registry import get_engine
from app.models.instance import Instance
from app.models.query import QueryLog
from app.models.slowlog import SlowQueryConfig, SlowQueryLog
from app.schemas.slowlog import (
    SlowQueryConfigItem,
    SlowQueryConfigUpdate,
    SlowQueryConfigUpsert,
    SlowQueryDistributionItem,
    SlowQueryEngineRow,
    SlowQueryExplainResponse,
    SlowQueryFingerprintDetailResponse,
    SlowQueryFingerprintItem,
    SlowQueryOverviewResponse,
    SlowQueryRecommendation,
    SlowQueryTrendPoint,
)
from app.services.monitor import MonitorService

DEFAULT_SLOW_THRESHOLD_MS = 1000
SUPPORTED_NATIVE_TYPES = {"mysql", "pgsql", "redis"}


def _as_int(value: Any) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def row_to_dict(columns: list[str], row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return {str(k): v for k, v in row.items()}
    if isinstance(row, (tuple, list)):
        return {columns[idx] if idx < len(columns) else str(idx): value for idx, value in enumerate(row)}
    return {"value": row}


def normalize_sql_fingerprint(sql: str) -> tuple[str, str]:
    """Return sha1 fingerprint and readable normalized SQL."""
    normalized = sql.strip()
    normalized = re.sub(r"'(?:''|[^'])*'", "?", normalized)
    normalized = re.sub(r'"(?:""|[^"])*"', "?", normalized)
    normalized = re.sub(r"\b\d+(?:\.\d+)?\b", "?", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip().rstrip(";")
    normalized = normalized[:2000]
    digest = hashlib.sha1(
        normalized.lower().encode(),
        usedforsecurity=False,
    ).hexdigest()
    return digest, normalized


def analyze_sql(sql: str, *, rows_examined: int = 0, rows_sent: int = 0, duration_ms: int = 0, source: str = "") -> list[str]:
    text = sql.strip().lower()
    tags: list[str] = []
    if "select *" in text:
        tags.append("SELECT *")
    if text.startswith("select") and " where " not in f" {text} ":
        tags.append("缺少 WHERE")
    if rows_examined >= 100000:
        tags.append("扫描行数高")
    if rows_sent >= 10000:
        tags.append("返回行数高")
    if duration_ms >= 10000:
        tags.append("超长耗时")
    if source == "platform" and ("export" in text or rows_sent >= 50000):
        tags.append("慢导出")
    if not tags:
        tags.append("需结合执行计划")
    return tags


def build_recommendations(
    sql: str,
    *,
    tags: list[str] | None = None,
    rows_examined: int = 0,
    rows_sent: int = 0,
    duration_ms: int = 0,
) -> list[SlowQueryRecommendation]:
    tags = tags or analyze_sql(sql, rows_examined=rows_examined, rows_sent=rows_sent, duration_ms=duration_ms)
    recs: list[SlowQueryRecommendation] = []
    if "SELECT *" in tags:
        recs.append(SlowQueryRecommendation(
            severity="warning",
            title="减少返回列",
            detail="查询使用 SELECT *，建议只返回业务必需字段，降低网络传输与行解码成本。",
        ))
    if "缺少 WHERE" in tags:
        recs.append(SlowQueryRecommendation(
            severity="critical",
            title="补充过滤条件",
            detail="SELECT 查询没有 WHERE 条件，容易触发全表扫描；请确认是否需要按时间、主键或业务维度过滤。",
        ))
    if "扫描行数高" in tags:
        recs.append(SlowQueryRecommendation(
            severity="critical",
            title="检查索引与过滤条件",
            detail="扫描行数较高，建议结合执行计划确认是否缺少索引、索引选择性不足或条件不可下推。",
        ))
    if "返回行数高" in tags:
        recs.append(SlowQueryRecommendation(
            severity="warning",
            title="控制结果集规模",
            detail="返回行数较高，建议分页、限制导出范围，或改为异步分批任务。",
        ))
    if "超长耗时" in tags:
        recs.append(SlowQueryRecommendation(
            severity="critical",
            title="优先分析执行计划",
            detail="耗时超过 10 秒，建议查看执行计划中的全表扫描、排序、临时表和 Join 顺序。",
        ))
    if not recs:
        recs.append(SlowQueryRecommendation(
            severity="info",
            title="结合执行计划确认瓶颈",
            detail="当前规则未命中明显风险，请查看执行计划、索引选择性和业务访问模式。",
        ))
    return recs


class SlowLogService:
    @staticmethod
    async def list_configs(db: AsyncSession, user: dict) -> tuple[int, list[SlowQueryConfigItem]]:
        result = await db.execute(
            select(Instance)
            .options(selectinload(Instance.resource_groups))
            .where(Instance.is_active.is_(True))
            .order_by(Instance.id.desc())
        )
        instances = [
            instance
            for instance in result.scalars().all()
            if SlowLogService.can_access_instance(user, instance)
        ]
        items: list[SlowQueryConfigItem] = []
        for instance in instances:
            cfg = await SlowLogService.ensure_default_config(db, instance, user)
            items.append(SlowQueryConfigItem(
                id=cfg.id,
                instance_id=cfg.instance_id,
                instance_name=instance.instance_name,
                db_type=instance.db_type,
                is_enabled=cfg.is_enabled,
                threshold_ms=cfg.threshold_ms,
                collect_interval=cfg.collect_interval,
                retention_days=cfg.retention_days,
                collect_limit=cfg.collect_limit,
                last_collect_at=cfg.last_collect_at,
                last_collect_status=cfg.last_collect_status,
                last_collect_error=cfg.last_collect_error,
                last_collect_count=cfg.last_collect_count,
                created_by=cfg.created_by,
            ))
        return len(items), items

    @staticmethod
    async def upsert_config(
        db: AsyncSession,
        data: SlowQueryConfigUpsert,
        user: dict,
    ) -> SlowQueryConfig:
        instance = await SlowLogService.get_instance_or_404(db, data.instance_id, user)
        result = await db.execute(select(SlowQueryConfig).where(SlowQueryConfig.instance_id == instance.id))
        cfg = result.scalar_one_or_none()
        if not cfg:
            cfg = SlowQueryConfig(instance_id=instance.id, created_by=user.get("username", ""))
            db.add(cfg)
        for field, value in data.model_dump(exclude={"instance_id"}).items():
            setattr(cfg, field, value)
        await db.commit()
        await db.refresh(cfg)
        return cfg

    @staticmethod
    async def update_config(
        db: AsyncSession,
        config_id: int,
        data: SlowQueryConfigUpdate,
        user: dict,
    ) -> SlowQueryConfig:
        result = await db.execute(
            select(SlowQueryConfig, Instance)
            .join(Instance, SlowQueryConfig.instance_id == Instance.id)
            .options(selectinload(Instance.resource_groups))
            .where(SlowQueryConfig.id == config_id)
        )
        row = result.first()
        if not row:
            raise NotFoundException("慢日志采集配置不存在")
        cfg, instance = row
        if not SlowLogService.can_access_instance(user, instance):
            raise AppException("无权修改该实例慢日志配置", code=403)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(cfg, field, value)
        await db.commit()
        await db.refresh(cfg)
        return cfg

    @staticmethod
    async def ensure_default_config(
        db: AsyncSession,
        instance: Instance,
        user: dict | None = None,
    ) -> SlowQueryConfig:
        result = await db.execute(select(SlowQueryConfig).where(SlowQueryConfig.instance_id == instance.id))
        cfg = result.scalar_one_or_none()
        if cfg:
            return cfg
        cfg = SlowQueryConfig(
            instance_id=instance.id,
            is_enabled=True,
            threshold_ms=DEFAULT_SLOW_THRESHOLD_MS,
            collect_interval=300,
            retention_days=30,
            collect_limit=100,
            created_by=(user or {}).get("username", "system"),
        )
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
        return cfg

    @staticmethod
    def can_access_instance(user: dict, instance: Instance) -> bool:
        return MonitorService._can_access_instance(user, instance)

    @staticmethod
    async def get_instance_or_404(db: AsyncSession, instance_id: int, user: dict) -> Instance:
        result = await db.execute(
            select(Instance)
            .options(selectinload(Instance.resource_groups))
            .where(Instance.id == instance_id, Instance.is_active.is_(True))
        )
        instance = result.scalar_one_or_none()
        if not instance:
            raise NotFoundException("实例不存在")
        if not SlowLogService.can_access_instance(user, instance):
            raise AppException("无权访问该实例慢日志", code=403)
        return instance

    @staticmethod
    async def scoped_instance_ids(db: AsyncSession, user: dict) -> list[int] | None:
        if user.get("is_superuser") or "monitor_all_instances" in user.get("permissions", []):
            return None
        rg_ids = user.get("resource_groups", [])
        if not rg_ids:
            return []
        from app.models.user import ResourceGroup

        result = await db.execute(
            select(Instance.id)
            .join(Instance.resource_groups.of_type(ResourceGroup))
            .where(ResourceGroup.id.in_(rg_ids), Instance.is_active.is_(True))
            .distinct()
        )
        return list(result.scalars().all())

    @staticmethod
    def _filters(
        stmt: Any,
        *,
        instance_id: int | None = None,
        db_name: str | None = None,
        source: str | None = None,
        sql_keyword: str | None = None,
        min_duration_ms: int = DEFAULT_SLOW_THRESHOLD_MS,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
        instance_ids: list[int] | None = None,
    ) -> Any:
        if instance_ids is not None:
            if not instance_ids:
                stmt = stmt.where(SlowQueryLog.instance_id == -1)
            else:
                stmt = stmt.where(SlowQueryLog.instance_id.in_(instance_ids))
        if instance_id:
            stmt = stmt.where(SlowQueryLog.instance_id == instance_id)
        if db_name:
            stmt = stmt.where(SlowQueryLog.db_name.ilike(f"%{db_name}%"))
        if source:
            stmt = stmt.where(SlowQueryLog.source == source)
        if sql_keyword:
            stmt = stmt.where(SlowQueryLog.sql_text.ilike(f"%{sql_keyword}%"))
        if min_duration_ms:
            stmt = stmt.where(SlowQueryLog.duration_ms >= min_duration_ms)
        if date_start:
            stmt = stmt.where(SlowQueryLog.occurred_at >= date_start)
        if date_end:
            stmt = stmt.where(SlowQueryLog.occurred_at <= date_end)
        return stmt

    @staticmethod
    async def sync_platform_logs(
        db: AsyncSession,
        *,
        threshold_ms: int = DEFAULT_SLOW_THRESHOLD_MS,
        since: datetime | None = None,
        instance_id: int | None = None,
    ) -> int:
        since = since or datetime.now(UTC) - timedelta(days=7)
        stmt = select(QueryLog).where(QueryLog.cost_time_ms >= threshold_ms, QueryLog.created_at >= since)
        if instance_id is not None:
            stmt = stmt.where(QueryLog.instance_id == instance_id)
        result = await db.execute(
            stmt.order_by(QueryLog.created_at.desc()).limit(1000)
        )
        logs = result.scalars().all()
        saved = 0
        for qlog in logs:
            source_ref = f"query_log:{qlog.id}"
            exists = await db.execute(
                select(SlowQueryLog.id).where(
                    SlowQueryLog.source == "platform",
                    SlowQueryLog.source_ref == source_ref,
                )
            )
            if exists.scalar_one_or_none():
                continue
            fingerprint, fingerprint_text = normalize_sql_fingerprint(qlog.sqllog)
            rows_sent = _as_int(qlog.effect_row)
            db.add(
                SlowQueryLog(
                    source="platform",
                    source_ref=source_ref,
                    instance_id=qlog.instance_id,
                    instance_name=qlog.instance_name,
                    db_type=qlog.db_type,
                    db_name=qlog.db_name,
                    sql_text=qlog.sqllog,
                    sql_fingerprint=fingerprint,
                    fingerprint_text=fingerprint_text,
                    duration_ms=_as_int(qlog.cost_time_ms),
                    rows_examined=0,
                    rows_sent=rows_sent,
                    username=qlog.username,
                    client_host=qlog.client_ip,
                    occurred_at=qlog.created_at,
                    raw={
                        "query_log_id": qlog.id,
                        "operation_type": qlog.operation_type,
                        "error": qlog.error,
                        "priv_check": qlog.priv_check,
                    },
                    analysis_tags=analyze_sql(
                        qlog.sqllog,
                        rows_sent=rows_sent,
                        duration_ms=_as_int(qlog.cost_time_ms),
                        source="platform",
                    ),
                    collect_error=qlog.error or "",
                )
            )
            saved += 1
        if saved:
            await db.commit()
        return saved

    @staticmethod
    async def list_logs(
        db: AsyncSession,
        user: dict,
        *,
        instance_id: int | None = None,
        db_name: str | None = None,
        source: str | None = None,
        sql_keyword: str | None = None,
        min_duration_ms: int = DEFAULT_SLOW_THRESHOLD_MS,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[int, list[SlowQueryLog]]:
        await SlowLogService.sync_platform_logs(db, threshold_ms=min_duration_ms, since=date_start)
        instance_ids = await SlowLogService.scoped_instance_ids(db, user)
        stmt = SlowLogService._filters(
            select(SlowQueryLog),
            instance_id=instance_id,
            db_name=db_name,
            source=source,
            sql_keyword=sql_keyword,
            min_duration_ms=min_duration_ms,
            date_start=date_start,
            date_end=date_end,
            instance_ids=instance_ids,
        )
        total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (
            await db.execute(
                stmt.order_by(SlowQueryLog.occurred_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return total, list(rows)

    @staticmethod
    async def overview(
        db: AsyncSession,
        user: dict,
        **filters: Any,
    ) -> SlowQueryOverviewResponse:
        await SlowLogService.sync_platform_logs(
            db,
            threshold_ms=filters.get("min_duration_ms") or DEFAULT_SLOW_THRESHOLD_MS,
            since=filters.get("date_start"),
        )
        instance_ids = await SlowLogService.scoped_instance_ids(db, user)
        stmt = SlowLogService._filters(select(SlowQueryLog), instance_ids=instance_ids, **filters)
        rows = (await db.execute(stmt.order_by(SlowQueryLog.occurred_at.desc()).limit(5000))).scalars().all()
        if not rows:
            return SlowQueryOverviewResponse()

        durations = sorted([_as_int(r.duration_ms) for r in rows])
        p95_idx = min(len(durations) - 1, int(len(durations) * 0.95))
        instance_count = len({r.instance_id for r in rows if r.instance_id is not None})
        total_duration = sum(durations)
        by_bucket: dict[str, list[SlowQueryLog]] = defaultdict(list)
        for row in rows:
            by_bucket[row.occurred_at.strftime("%Y-%m-%d %H:00")].append(row)
        trends = [
            SlowQueryTrendPoint(
                bucket=bucket,
                count=len(items),
                avg_duration_ms=int(sum(_as_int(i.duration_ms) for i in items) / len(items)),
                failed_count=sum(1 for i in items if i.collect_error),
            )
            for bucket, items in sorted(by_bucket.items())[-48:]
        ]
        slowest = max(rows, key=lambda r: _as_int(r.duration_ms))
        return SlowQueryOverviewResponse(
            total=len(rows),
            instance_count=instance_count,
            avg_duration_ms=int(total_duration / len(rows)),
            p95_duration_ms=durations[p95_idx],
            max_duration_ms=durations[-1],
            slowest=slowest,
            trends=trends,
        )

    @staticmethod
    async def fingerprints(
        db: AsyncSession,
        user: dict,
        *,
        limit: int = 20,
        **filters: Any,
    ) -> list[SlowQueryFingerprintItem]:
        await SlowLogService.sync_platform_logs(
            db,
            threshold_ms=filters.get("min_duration_ms") or DEFAULT_SLOW_THRESHOLD_MS,
            since=filters.get("date_start"),
        )
        instance_ids = await SlowLogService.scoped_instance_ids(db, user)
        stmt = SlowLogService._filters(select(SlowQueryLog), instance_ids=instance_ids, **filters)
        rows = (await db.execute(stmt.order_by(SlowQueryLog.occurred_at.desc()).limit(10000))).scalars().all()
        grouped: dict[str, list[SlowQueryLog]] = defaultdict(list)
        for row in rows:
            grouped[row.sql_fingerprint].append(row)

        items: list[SlowQueryFingerprintItem] = []
        for fp, fp_rows in grouped.items():
            durations = sorted(_as_int(row.duration_ms) for row in fp_rows)
            p95_idx = min(len(durations) - 1, int(len(durations) * 0.95))
            latest = max(fp_rows, key=lambda row: row.occurred_at)
            tags = sorted({tag for row in fp_rows for tag in (row.analysis_tags or [])})
            items.append(
                SlowQueryFingerprintItem(
                    sql_fingerprint=fp,
                    fingerprint_text=latest.fingerprint_text,
                    sample_sql=latest.sql_text,
                    count=len(fp_rows),
                    avg_duration_ms=int(sum(durations) / len(durations)),
                    max_duration_ms=durations[-1],
                    p95_duration_ms=durations[p95_idx],
                    rows_examined=sum(_as_int(row.rows_examined) for row in fp_rows),
                    rows_sent=sum(_as_int(row.rows_sent) for row in fp_rows),
                    analysis_tags=tags,
                    last_seen_at=latest.occurred_at,
                )
            )
        return sorted(items, key=lambda item: (item.avg_duration_ms, item.count), reverse=True)[:limit]

    @staticmethod
    def _fingerprint_from_rows(fp: str, fp_rows: list[SlowQueryLog]) -> SlowQueryFingerprintItem:
        durations = sorted(_as_int(row.duration_ms) for row in fp_rows)
        p95_idx = min(len(durations) - 1, int(len(durations) * 0.95))
        latest = max(fp_rows, key=lambda row: row.occurred_at)
        tags = sorted({tag for row in fp_rows for tag in (row.analysis_tags or [])})
        return SlowQueryFingerprintItem(
            sql_fingerprint=fp,
            fingerprint_text=latest.fingerprint_text,
            sample_sql=latest.sql_text,
            count=len(fp_rows),
            avg_duration_ms=int(sum(durations) / len(durations)),
            max_duration_ms=durations[-1],
            p95_duration_ms=durations[p95_idx],
            rows_examined=sum(_as_int(row.rows_examined) for row in fp_rows),
            rows_sent=sum(_as_int(row.rows_sent) for row in fp_rows),
            analysis_tags=tags,
            last_seen_at=latest.occurred_at,
        )

    @staticmethod
    def _distribution(rows: list[SlowQueryLog], attr: str, fallback: str = "unknown") -> list[SlowQueryDistributionItem]:
        grouped: dict[str, list[SlowQueryLog]] = defaultdict(list)
        for row in rows:
            grouped[_string(getattr(row, attr, "")) or fallback].append(row)
        items = [
            SlowQueryDistributionItem(
                name=name,
                count=len(items),
                avg_duration_ms=int(sum(_as_int(item.duration_ms) for item in items) / len(items)),
            )
            for name, items in grouped.items()
        ]
        return sorted(items, key=lambda item: item.count, reverse=True)[:10]

    @staticmethod
    async def fingerprint_detail(
        db: AsyncSession,
        user: dict,
        fingerprint: str,
        *,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> SlowQueryFingerprintDetailResponse:
        instance_ids = await SlowLogService.scoped_instance_ids(db, user)
        stmt = select(SlowQueryLog).where(SlowQueryLog.sql_fingerprint == fingerprint)
        stmt = SlowLogService._filters(stmt, date_start=date_start, date_end=date_end, min_duration_ms=0, instance_ids=instance_ids)
        rows = (await db.execute(stmt.order_by(SlowQueryLog.occurred_at.desc()).limit(5000))).scalars().all()
        if not rows:
            raise NotFoundException("慢 SQL 指纹不存在或无权访问")

        fp_item = SlowLogService._fingerprint_from_rows(fingerprint, list(rows))
        by_bucket: dict[str, list[SlowQueryLog]] = defaultdict(list)
        for row in rows:
            by_bucket[row.occurred_at.strftime("%Y-%m-%d %H:00")].append(row)
        trends = [
            SlowQueryTrendPoint(
                bucket=bucket,
                count=len(items),
                avg_duration_ms=int(sum(_as_int(i.duration_ms) for i in items) / len(items)),
                failed_count=sum(1 for i in items if i.collect_error),
            )
            for bucket, items in sorted(by_bucket.items())[-48:]
        ]
        sample_rows = list(rows[:20])
        return SlowQueryFingerprintDetailResponse(
            fingerprint=fp_item,
            trends=trends,
            instance_distribution=SlowLogService._distribution(list(rows), "instance_name"),
            database_distribution=SlowLogService._distribution(list(rows), "db_name", "default"),
            user_distribution=SlowLogService._distribution(list(rows), "username", "unknown"),
            source_distribution=SlowLogService._distribution(list(rows), "source"),
            recommendations=build_recommendations(
                fp_item.sample_sql,
                tags=fp_item.analysis_tags,
                rows_examined=fp_item.rows_examined,
                rows_sent=fp_item.rows_sent,
                duration_ms=fp_item.max_duration_ms,
            ),
            samples=sample_rows,
        )

    @staticmethod
    async def samples(
        db: AsyncSession,
        user: dict,
        fingerprint: str,
        limit: int = 20,
    ) -> list[SlowQueryLog]:
        instance_ids = await SlowLogService.scoped_instance_ids(db, user)
        stmt = select(SlowQueryLog).where(SlowQueryLog.sql_fingerprint == fingerprint)
        if instance_ids is not None:
            if not instance_ids:
                stmt = stmt.where(SlowQueryLog.instance_id == -1)
            else:
                stmt = stmt.where(SlowQueryLog.instance_id.in_(instance_ids))
        rows = (
            await db.execute(stmt.order_by(SlowQueryLog.duration_ms.desc(), SlowQueryLog.occurred_at.desc()).limit(limit))
        ).scalars().all()
        return list(rows)

    @staticmethod
    def _is_explain_safe(sql: str) -> bool:
        text = sql.strip().lower()
        return text.startswith("select ") or text.startswith("with ")

    @staticmethod
    def _extract_raw_plan(rs: ResultSet) -> Any:
        if not rs.rows:
            return None
        row = rs.rows[0]
        if isinstance(row, dict):
            value = row.get("EXPLAIN") or row.get("QUERY PLAN") or next(iter(row.values()), None)
        elif isinstance(row, (tuple, list)):
            value = row[0] if row else None
        else:
            value = row
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    @staticmethod
    def _walk_plan(node: Any) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        if isinstance(node, list):
            for item in node:
                nodes.extend(SlowLogService._walk_plan(item))
        elif isinstance(node, dict):
            nodes.append(node)
            for key in ("Plan", "Plans", "plans", "nested_loop", "query_block", "table", "ordering_operation", "grouping_operation"):
                child = node.get(key)
                if child is not None:
                    nodes.extend(SlowLogService._walk_plan(child))
        return nodes

    @staticmethod
    def analyze_plan(db_type: str, raw_plan: Any) -> tuple[dict[str, Any], list[SlowQueryRecommendation]]:
        nodes = SlowLogService._walk_plan(raw_plan)
        recs: list[SlowQueryRecommendation] = []
        summary: dict[str, Any] = {
            "node_count": len(nodes),
            "full_scan": False,
            "filesort": False,
            "temporary": False,
            "nested_loop": False,
            "max_cost": 0,
            "rows_estimate": 0,
        }
        for node in nodes:
            text = json.dumps(node, ensure_ascii=False).lower()
            node_type = _string(node.get("Node Type") or node.get("access_type") or node.get("using_join_buffer"))
            if node_type.lower() in {"seq scan", "all"} or '"access_type": "all"' in text:
                summary["full_scan"] = True
            if "filesort" in text:
                summary["filesort"] = True
            if "temporary" in text:
                summary["temporary"] = True
            if "nested loop" in node_type.lower():
                summary["nested_loop"] = True
            summary["max_cost"] = max(summary["max_cost"], _as_int(node.get("Total Cost") or node.get("query_cost")))
            summary["rows_estimate"] = max(summary["rows_estimate"], _as_int(node.get("Plan Rows") or node.get("rows_examined_per_scan") or node.get("rows_produced_per_join")))

        if summary["full_scan"]:
            recs.append(SlowQueryRecommendation(
                severity="critical",
                title="执行计划存在全表扫描",
                detail="计划中出现 Seq Scan 或 access_type=ALL，建议检查 WHERE 条件、索引覆盖和统计信息。",
            ))
        if summary["filesort"] or summary["temporary"]:
            recs.append(SlowQueryRecommendation(
                severity="warning",
                title="存在排序或临时表开销",
                detail="计划中出现 filesort/temporary，建议检查 ORDER BY/GROUP BY 字段索引或减少中间结果集。",
            ))
        if summary["nested_loop"] and summary["rows_estimate"] >= 10000:
            recs.append(SlowQueryRecommendation(
                severity="warning",
                title="Nested Loop 行数估算较高",
                detail="Nested Loop 在高行数场景可能放大耗时，建议确认 Join 条件索引与表连接顺序。",
            ))
        if not recs:
            recs.append(SlowQueryRecommendation(
                severity="info",
                title="未发现明显执行计划风险",
                detail=f"{db_type.upper()} 执行计划未命中内置高风险规则，建议结合业务峰值和索引选择性继续判断。",
            ))
        return summary, recs

    @staticmethod
    async def explain(
        db: AsyncSession,
        user: dict,
        *,
        log_id: int | None = None,
        instance_id: int | None = None,
        db_name: str = "",
        sql: str = "",
    ) -> SlowQueryExplainResponse:
        log: SlowQueryLog | None = None
        if log_id:
            result = await db.execute(select(SlowQueryLog).where(SlowQueryLog.id == log_id))
            log = result.scalar_one_or_none()
            if not log:
                raise NotFoundException("慢 SQL 记录不存在")
            instance_id = log.instance_id
            db_name = log.db_name
            sql = log.sql_text
        if not instance_id:
            raise AppException("缺少 instance_id", code=422)
        if not sql.strip():
            raise AppException("SQL 不能为空", code=422)
        instance = await SlowLogService.get_instance_or_404(db, instance_id, user)
        if instance.db_type not in {"mysql", "pgsql"}:
            return SlowQueryExplainResponse(
                supported=False,
                db_type=instance.db_type,
                msg=f"{instance.db_type} 暂不支持执行计划分析",
            )
        if not SlowLogService._is_explain_safe(sql):
            return SlowQueryExplainResponse(
                supported=False,
                db_type=instance.db_type,
                msg="仅支持 SELECT/WITH 查询的执行计划分析",
            )
        engine = get_engine(instance)
        rs = await engine.explain_query(db_name or instance.db_name, sql)
        if rs.error:
            return SlowQueryExplainResponse(supported=True, db_type=instance.db_type, msg=rs.error)
        raw_plan = SlowLogService._extract_raw_plan(rs)
        summary, recs = SlowLogService.analyze_plan(instance.db_type, raw_plan)
        if log:
            recs = build_recommendations(
                log.sql_text,
                tags=log.analysis_tags,
                rows_examined=log.rows_examined,
                rows_sent=log.rows_sent,
                duration_ms=log.duration_ms,
            ) + recs
        return SlowQueryExplainResponse(
            supported=True,
            db_type=instance.db_type,
            summary=recs,
            plan=summary,
            raw=raw_plan,
            msg="",
        )

    @staticmethod
    async def save_engine_rows(
        db: AsyncSession,
        instance: Instance,
        rows: list[SlowQueryEngineRow],
    ) -> int:
        saved = 0
        now = datetime.now(UTC)
        for item in rows:
            fingerprint, fingerprint_text = normalize_sql_fingerprint(item.sql_text)
            occurred = item.occurred_at or now
            source_ref = item.source_ref or hashlib.sha1(
                f"{instance.id}:{item.source}:{fingerprint}:{occurred}".encode(),
                usedforsecurity=False,
            ).hexdigest()
            if item.source != "platform":
                source_ref = f"{instance.id}:{source_ref}"
            if item.source in {"mysql_slowlog", "pgsql_statements"}:
                source_ref = f"{source_ref}:{occurred.strftime('%Y%m%d%H%M')}"
            exists = await db.execute(
                select(SlowQueryLog.id).where(
                    SlowQueryLog.source == item.source,
                    SlowQueryLog.source_ref == source_ref,
                )
            )
            if exists.scalar_one_or_none():
                continue
            db.add(
                SlowQueryLog(
                    source=item.source,
                    source_ref=source_ref,
                    instance_id=instance.id,
                    instance_name=instance.instance_name,
                    db_type=instance.db_type,
                    db_name=item.db_name or instance.db_name or "",
                    sql_text=item.sql_text,
                    sql_fingerprint=fingerprint,
                    fingerprint_text=fingerprint_text,
                    duration_ms=item.duration_ms,
                    rows_examined=item.rows_examined,
                    rows_sent=item.rows_sent,
                    username=item.username,
                    client_host=item.client_host,
                    occurred_at=occurred,
                    raw=item.raw,
                    analysis_tags=analyze_sql(
                        item.sql_text,
                        rows_examined=item.rows_examined,
                        rows_sent=item.rows_sent,
                        duration_ms=item.duration_ms,
                        source=item.source,
                    ),
                )
            )
            saved += 1
        if saved:
            await db.commit()
        return saved

    @staticmethod
    async def collect_instance(
        db: AsyncSession,
        instance: Instance,
        *,
        limit: int = 100,
        since: datetime | None = None,
        config: SlowQueryConfig | None = None,
    ) -> tuple[int, str]:
        config = config or await SlowLogService.ensure_default_config(db, instance)
        if not config.is_enabled:
            config.last_collect_at = datetime.now(UTC)
            config.last_collect_status = "disabled"
            config.last_collect_error = ""
            config.last_collect_count = 0
            await db.commit()
            return 0, "慢日志采集未启用"
        limit = min(limit, config.collect_limit)
        if instance.db_type not in SUPPORTED_NATIVE_TYPES:
            config.last_collect_at = datetime.now(UTC)
            config.last_collect_status = "unsupported"
            config.last_collect_error = f"{instance.db_type} 暂不支持原生慢日志采集"
            config.last_collect_count = 0
            await db.commit()
            return 0, f"{instance.db_type} 暂不支持原生慢日志采集"
        engine = get_engine(instance)
        if not hasattr(engine, "collect_slow_queries"):
            config.last_collect_at = datetime.now(UTC)
            config.last_collect_status = "unsupported"
            config.last_collect_error = f"{instance.db_type} 暂不支持原生慢日志采集"
            config.last_collect_count = 0
            await db.commit()
            return 0, f"{instance.db_type} 暂不支持原生慢日志采集"
        rs = await engine.collect_slow_queries(since=since, limit=limit)
        if rs.error:
            config.last_collect_at = datetime.now(UTC)
            config.last_collect_status = "failed"
            config.last_collect_error = rs.error
            config.last_collect_count = 0
            await db.commit()
            return 0, rs.error
        rows = SlowLogService.normalize_engine_result(instance, rs)
        rows = [row for row in rows if row.duration_ms >= config.threshold_ms]
        saved = await SlowLogService.save_engine_rows(db, instance, rows)
        config.last_collect_at = datetime.now(UTC)
        config.last_collect_status = "success"
        config.last_collect_error = ""
        config.last_collect_count = saved
        await db.commit()
        return saved, ""

    @staticmethod
    def normalize_engine_result(instance: Instance, rs: ResultSet) -> list[SlowQueryEngineRow]:
        normalized: list[SlowQueryEngineRow] = []
        for row in rs.rows:
            raw = row_to_dict(rs.column_list or [], row)
            lowered = {k.lower(): v for k, v in raw.items()}
            source = _string(lowered.get("source")) or {
                "mysql": "mysql_slowlog",
                "pgsql": "pgsql_statements",
                "redis": "redis_slowlog",
            }.get(instance.db_type, f"{instance.db_type}_slowlog")
            sql_text = _string(
                lowered.get("sql_text")
                or lowered.get("query")
                or lowered.get("digest_text")
                or lowered.get("command")
                or lowered.get("info")
            )
            if not sql_text:
                continue
            normalized.append(
                SlowQueryEngineRow(
                    source=source,
                    source_ref=_string(lowered.get("source_ref") or lowered.get("id") or lowered.get("queryid")),
                    db_name=_string(lowered.get("db_name") or lowered.get("db") or lowered.get("datname")),
                    sql_text=sql_text,
                    duration_ms=_as_int(lowered.get("duration_ms") or lowered.get("avg_ms") or lowered.get("mean_exec_time") or lowered.get("duration_us")) // (1000 if lowered.get("duration_us") else 1),
                    rows_examined=_as_int(lowered.get("rows_examined")),
                    rows_sent=_as_int(lowered.get("rows_sent") or lowered.get("rows")),
                    username=_string(lowered.get("username") or lowered.get("user") or lowered.get("usename")),
                    client_host=_string(lowered.get("client_host") or lowered.get("host")),
                    raw={k: _string(v) for k, v in raw.items()},
                )
            )
        return normalized

    @staticmethod
    async def cleanup_old_logs(db: AsyncSession, retention_days: int = 30) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        result = await db.execute(delete(SlowQueryLog).where(SlowQueryLog.occurred_at < cutoff))
        return result.rowcount or 0
