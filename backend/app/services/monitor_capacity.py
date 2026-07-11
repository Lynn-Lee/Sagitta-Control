"""观测中心容量域服务：库/表容量快照的采集、查询与增长分析。

从 `MonitorService` 拆出的叶子模块（配合 `monitor_alerts.py` 的门面委托范式，见评估 #7）。
实例访问鉴权（`check_privilege`）保留在 `MonitorService` 门面完成，本模块只承载容量数据的
采集 / 查询 / 归一逻辑，故不反向依赖门面，避免循环导入。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.instance import Instance, InstanceDatabase
from app.models.monitor import (
    MonitorCollectConfig,
    MonitorDatabaseCapacitySnapshot,
    MonitorMetricSnapshot,
    MonitorTableCapacitySnapshot,
)


class MonitorCapacityService:
    """库/表容量域：快照采集、最新容量查询、增长分析与容量风险判定。"""

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

    # --- 读查询（鉴权由 MonitorService 门面完成后调用）---

    @staticmethod
    async def database_capacity(db: AsyncSession, instance_id: int) -> list[dict[str, Any]]:
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
    async def table_capacity(
        db: AsyncSession,
        instance_id: int,
        db_name: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[int, list[dict[str, Any]]]:
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
    async def capacity_growth(db: AsyncSession, instance_id: int, days: int = 7) -> dict[str, Any]:
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
        db_growth: list[dict[str, Any]] = [
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
        table_total, tables = await MonitorCapacityService.table_capacity(
            db, instance_id, page_size=20
        )
        return {
            "top_databases": db_growth[:20],
            "top_tables": tables,
            "table_total": table_total,
            "days": days,
        }

    @staticmethod
    def has_capacity_risk(snapshot: dict[str, Any]) -> bool:
        extra = snapshot.get("extra_metrics") or {}
        tablespaces = extra.get("tablespaces") or []
        if any(
            (MonitorCapacityService._coerce_float(item.get("used_pct")) or 0) >= 80
            for item in tablespaces
        ):
            return True
        disks = extra.get("disks") or []
        if any(
            (MonitorCapacityService._coerce_float(item.get("used_pct")) or 0) >= 80
            for item in disks
        ):
            return True
        fra = extra.get("fra") or {}
        return (MonitorCapacityService._coerce_float(fra.get("used_pct")) or 0) >= 80

    # --- 采集 ---

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
        db_names = await MonitorCapacityService._capacity_database_names(db, engine, inst)
        instance_total = 0
        for db_name in db_names:
            try:
                metas = await engine.get_tables_metas_data(db_name)
                table_rows = [
                    MonitorCapacityService._normalize_table_capacity(inst.id, db_name, meta, now)
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
        return [
            name for name in names if name.lower() not in MonitorCapacityService.SYSTEM_DATABASES
        ]

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
        data_size = MonitorCapacityService._int_value(
            lowered.get("data_length")
            or lowered.get("data_size")
            or lowered.get("data_bytes")
            or lowered.get("size")
            or 0
        )
        index_size = MonitorCapacityService._int_value(
            lowered.get("index_length") or lowered.get("index_size") or 0
        )
        total_size = MonitorCapacityService._int_value(
            lowered.get("total_size")
            or lowered.get("total_bytes")
            or lowered.get("bytes")
            or lowered.get("storage_size")
            or data_size + index_size
        )
        if not data_size and total_size and index_size:
            data_size = max(total_size - index_size, 0)
        row_count = MonitorCapacityService._int_value(
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
            extra=MonitorCapacityService._json_safe(meta),
        )

    # --- 本地工具（trivial pure；沿用 monitor_alerts 叶子自带 _coerce_float 的约定，保持叶子自洽）---

    @staticmethod
    def _int_value(value: Any) -> int:
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0

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
            return {str(k): MonitorCapacityService._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [MonitorCapacityService._json_safe(v) for v in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return int(value) if value == value.to_integral_value() else float(value)
        return value
