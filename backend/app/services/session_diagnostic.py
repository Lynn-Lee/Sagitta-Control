"""Session diagnostics and history helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.engines.models import ResultSet
from app.models.instance import Instance
from app.models.session import SessionCollectConfig, SessionSnapshot
from app.schemas.diagnostic import (
    SessionCollectConfigItem,
    SessionCollectConfigUpdate,
    SessionCollectConfigUpsert,
    SessionItem,
)

DEFAULT_SESSION_COLLECT_INTERVAL = 60
DEFAULT_SESSION_RETENTION_DAYS = 30

_ONLINE_COLUMNS = [
    "session_id",
    "serial",
    "username",
    "host",
    "program",
    "db_name",
    "command",
    "state",
    "time_seconds",
    "connection_age_ms",
    "state_duration_ms",
    "active_duration_ms",
    "transaction_age_ms",
    "sql_id",
    "sql_text",
    "event",
    "blocking_session",
]


def _clean_key(key: str) -> str:
    return key.strip().lower().replace("#", "").replace(" ", "_").replace("-", "_")


def _string(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "read"):
        try:
            value = value.read()
        except Exception:
            return str(value)
    return str(value)


def _int(value: Any) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _duration_ms(raw: dict[str, Any]) -> int:
    direct_ms = _float(_pick(raw, "duration_ms", "elapsed_ms", "time_ms"))
    if direct_ms is not None:
        return max(0, int(round(direct_ms)))

    duration_us = _float(_pick(raw, "duration_us", "elapsed_us", "time_us"))
    if duration_us is not None:
        return max(0, int(round(duration_us / 1000)))

    elapsed_sec = _float(
        _pick(raw, "elapsed_sec", "seconds", "time_seconds", "time", "last_call_et", "secs_running", "elapsed")
    )
    if elapsed_sec is not None:
        return max(0, int(round(elapsed_sec * 1000)))

    return 0


def _optional_duration_ms(raw: dict[str, Any], *keys: str) -> int | None:
    value = _float(_pick(raw, *keys))
    if value is None:
        return None
    return max(0, int(round(value)))


def row_to_dict(columns: list[str], row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return {str(k): v for k, v in row.items()}
    if isinstance(row, (tuple, list)):
        return {columns[idx] if idx < len(columns) else str(idx): value for idx, value in enumerate(row)}
    return {"value": row}


def _pick(row: dict[str, Any], *keys: str) -> Any:
    normalized = {_clean_key(k): v for k, v in row.items()}
    for key in keys:
        value = normalized.get(_clean_key(key))
        if value not in (None, ""):
            return value
    return ""


def normalize_session_row(
    *,
    instance: Instance,
    columns: list[str],
    row: Any,
    collected_at: datetime | None = None,
    source: str = "online",
) -> SessionItem:
    raw = row_to_dict(columns, row)
    db_type = instance.db_type

    item = SessionItem(
        instance_id=instance.id,
        instance_name=instance.instance_name,
        db_type=db_type,
        collected_at=collected_at,
        source=source,
        raw={k: _string(v) for k, v in raw.items()},
    )

    item.session_id = _string(_pick(raw, "session_id", "sid", "pid", "id", "query_id", "opid"))
    item.serial = _string(_pick(raw, "serial", "serial#", "serial_number"))
    item.username = _string(_pick(raw, "username", "user", "usename"))
    item.host = _string(_pick(raw, "host", "machine", "client_addr", "client_hostname"))
    item.program = _string(_pick(raw, "program", "application_name", "desc", "type"))
    item.db_name = _string(_pick(raw, "db_name", "db", "datname", "schema", "ns"))
    item.command = _string(_pick(raw, "command", "cmd", "type"))
    item.state = _string(_pick(raw, "state", "status", "wait_class"))
    item.connection_age_ms = _optional_duration_ms(raw, "connection_age_ms", "connection_ms", "session_age_ms")
    item.state_duration_ms = _optional_duration_ms(raw, "state_duration_ms", "duration_ms", "elapsed_ms", "time_ms")
    if item.state_duration_ms is None:
        item.state_duration_ms = _duration_ms(raw)
    item.active_duration_ms = _optional_duration_ms(raw, "active_duration_ms", "query_duration_ms", "sql_duration_ms")
    item.transaction_age_ms = _optional_duration_ms(raw, "transaction_age_ms", "xact_age_ms")
    item.duration_source = _string(_pick(raw, "duration_source"))
    item.duration_ms = item.state_duration_ms or 0
    item.time_seconds = item.duration_ms // 1000
    item.sql_id = _string(_pick(raw, "sql_id", "query_id"))
    item.sql_text = _string(_pick(raw, "sql_text", "sql_fulltext", "query", "info"))
    item.event = _string(_pick(raw, "event"))
    item.blocking_session = _string(_pick(raw, "blocking_session"))

    if not item.command and db_type == "pgsql":
        item.command = "Query"
    if not item.command and db_type == "clickhouse":
        item.command = "Query"
    if not item.state and item.command:
        item.state = item.command
    return item


def items_to_legacy_rows(items: list[SessionItem]) -> tuple[list[str], list[list[Any]]]:
    rows: list[list[Any]] = []
    for item in items:
        rows.append([getattr(item, col) for col in _ONLINE_COLUMNS])
    return _ONLINE_COLUMNS, rows


def is_collect_due(cfg: Any, now: datetime) -> bool:
    if not getattr(cfg, "is_enabled", True):
        return False
    last_collect_at = getattr(cfg, "last_collect_at", None)
    if not last_collect_at:
        return True
    return now - last_collect_at >= timedelta(seconds=int(getattr(cfg, "collect_interval", DEFAULT_SESSION_COLLECT_INTERVAL)))


class SessionDiagnosticService:
    @staticmethod
    def can_access_instance(user: dict, instance: Instance) -> bool:
        if user.get("is_superuser") or "query_all_instances" in user.get("permissions", []):
            return True
        user_rg_ids = set(user.get("resource_groups") or [])
        instance_rg_ids = {rg.id for rg in getattr(instance, "resource_groups", [])}
        return bool(user_rg_ids & instance_rg_ids)

    @staticmethod
    async def get_instance_or_404(db: AsyncSession, instance_id: int, user: dict | None = None) -> Instance:
        from fastapi import HTTPException

        result = await db.execute(
            select(Instance)
            .options(selectinload(Instance.resource_groups))
            .where(Instance.id == instance_id, Instance.is_active.is_(True))
        )
        instance = result.scalar_one_or_none()
        if not instance:
            raise HTTPException(404, f"实例 ID={instance_id} 不存在")
        if user is not None and not SessionDiagnosticService.can_access_instance(user, instance):
            raise HTTPException(403, "无权访问该实例")
        return instance

    @staticmethod
    async def ensure_default_config(
        db: AsyncSession,
        instance: Instance,
        user: dict | None = None,
    ) -> SessionCollectConfig:
        result = await db.execute(
            select(SessionCollectConfig).where(SessionCollectConfig.instance_id == instance.id)
        )
        cfg = result.scalar_one_or_none()
        if cfg:
            return cfg
        cfg = SessionCollectConfig(
            instance_id=instance.id,
            is_enabled=True,
            collect_interval=DEFAULT_SESSION_COLLECT_INTERVAL,
            retention_days=DEFAULT_SESSION_RETENTION_DAYS,
            last_collect_status="never",
            created_by=(user or {}).get("username", ""),
        )
        db.add(cfg)
        await db.flush()
        return cfg

    @staticmethod
    async def list_configs(db: AsyncSession, user: dict) -> tuple[int, list[SessionCollectConfigItem]]:
        instance_stmt = (
            select(Instance)
            .options(selectinload(Instance.resource_groups))
            .where(Instance.is_active.is_(True))
            .order_by(Instance.id.desc())
        )
        instances = (await db.execute(instance_stmt)).scalars().all()
        items: list[SessionCollectConfigItem] = []
        for inst in instances:
            if not SessionDiagnosticService.can_access_instance(user, inst):
                continue
            cfg = await SessionDiagnosticService.ensure_default_config(db, inst, user)
            items.append(
                SessionCollectConfigItem(
                    id=cfg.id,
                    instance_id=inst.id,
                    instance_name=inst.instance_name,
                    db_type=inst.db_type,
                    is_enabled=cfg.is_enabled,
                    collect_interval=cfg.collect_interval,
                    retention_days=cfg.retention_days,
                    last_collect_at=cfg.last_collect_at,
                    last_collect_status=cfg.last_collect_status,
                    last_collect_error=cfg.last_collect_error,
                    last_collect_count=cfg.last_collect_count,
                    created_by=cfg.created_by,
                )
            )
        await db.commit()
        return len(items), items

    @staticmethod
    async def upsert_config(
        db: AsyncSession,
        data: SessionCollectConfigUpsert,
        user: dict,
    ) -> SessionCollectConfig:
        instance = await SessionDiagnosticService.get_instance_or_404(db, data.instance_id, user)
        cfg = await SessionDiagnosticService.ensure_default_config(db, instance, user)
        cfg.is_enabled = data.is_enabled
        cfg.collect_interval = data.collect_interval
        cfg.retention_days = data.retention_days
        if not cfg.created_by:
            cfg.created_by = user.get("username", "")
        await db.commit()
        await db.refresh(cfg)
        return cfg

    @staticmethod
    async def update_config(
        db: AsyncSession,
        config_id: int,
        data: SessionCollectConfigUpdate,
        user: dict,
    ) -> SessionCollectConfig:
        from fastapi import HTTPException

        result = await db.execute(
            select(SessionCollectConfig, Instance)
            .join(Instance, SessionCollectConfig.instance_id == Instance.id)
            .options(selectinload(Instance.resource_groups))
            .where(SessionCollectConfig.id == config_id)
        )
        row = result.first()
        if not row:
            raise HTTPException(404, "会话采集配置不存在")
        cfg, instance = row
        if not SessionDiagnosticService.can_access_instance(user, instance):
            raise HTTPException(403, "无权修改该实例会话采集配置")
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(cfg, field, value)
        await db.commit()
        await db.refresh(cfg)
        return cfg

    @staticmethod
    def normalize_result(instance: Instance, rs: ResultSet, source: str = "online") -> list[SessionItem]:
        now = datetime.now(UTC)
        return [
            normalize_session_row(
                instance=instance,
                columns=rs.column_list or [],
                row=row,
                collected_at=now,
                source=source,
            )
            for row in rs.rows
        ]

    @staticmethod
    async def save_snapshot(
        db: AsyncSession,
        instance: Instance,
        rs: ResultSet,
        collected_at: datetime | None = None,
    ) -> int:
        collected = collected_at or datetime.now(UTC)
        if rs.error:
            db.add(
                SessionSnapshot(
                    collected_at=collected,
                    instance_id=instance.id,
                    instance_name=instance.instance_name,
                    db_type=instance.db_type,
                    source="platform",
                    collect_error=rs.error,
                    raw={},
                )
            )
            return 1

        count = 0
        for item in SessionDiagnosticService.normalize_result(instance, rs, source="platform"):
            db.add(
                SessionSnapshot(
                    collected_at=collected,
                    instance_id=instance.id,
                    instance_name=instance.instance_name,
                    db_type=instance.db_type,
                    session_id=item.session_id,
                    serial=item.serial,
                    username=item.username,
                    host=item.host,
                    program=item.program,
                    db_name=item.db_name,
                    command=item.command,
                    state=item.state,
                    time_seconds=item.time_seconds,
                    duration_ms=item.duration_ms,
                    connection_age_ms=item.connection_age_ms,
                    state_duration_ms=item.state_duration_ms,
                    active_duration_ms=item.active_duration_ms,
                    transaction_age_ms=item.transaction_age_ms,
                    duration_source=item.duration_source,
                    sql_id=item.sql_id,
                    sql_text=item.sql_text,
                    event=item.event,
                    blocking_session=item.blocking_session,
                    source="platform",
                    collect_error="",
                    raw=item.raw,
                )
            )
            count += 1
        return count

    @staticmethod
    async def list_history(
        db: AsyncSession,
        *,
        instance_id: int | None = None,
        db_type: str | None = None,
        username: str | None = None,
        db_name: str | None = None,
        state: str | None = None,
        command: str | None = None,
        sql_keyword: str | None = None,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
        min_seconds: int | None = None,
        min_duration_ms: int | None = None,
        min_connection_age_ms: int | None = None,
        min_state_duration_ms: int | None = None,
        min_active_duration_ms: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[int, list[SessionItem]]:
        stmt = select(SessionSnapshot)
        if instance_id:
            stmt = stmt.where(SessionSnapshot.instance_id == instance_id)
        if db_type:
            stmt = stmt.where(SessionSnapshot.db_type == db_type)
        if username:
            stmt = stmt.where(SessionSnapshot.username.ilike(f"%{username}%"))
        if db_name:
            stmt = stmt.where(SessionSnapshot.db_name.ilike(f"%{db_name}%"))
        if state:
            stmt = stmt.where(SessionSnapshot.state.ilike(f"%{state}%"))
        if command:
            stmt = stmt.where(SessionSnapshot.command.ilike(f"%{command}%"))
        if sql_keyword:
            stmt = stmt.where(SessionSnapshot.sql_text.ilike(f"%{sql_keyword}%"))
        if date_start:
            stmt = stmt.where(SessionSnapshot.collected_at >= date_start)
        if date_end:
            stmt = stmt.where(SessionSnapshot.collected_at <= date_end)
        if min_connection_age_ms is not None:
            stmt = stmt.where(SessionSnapshot.connection_age_ms >= min_connection_age_ms)
        if min_state_duration_ms is not None:
            stmt = stmt.where(SessionSnapshot.state_duration_ms >= min_state_duration_ms)
        if min_active_duration_ms is not None:
            stmt = stmt.where(SessionSnapshot.active_duration_ms >= min_active_duration_ms)
        if min_duration_ms is not None:
            stmt = stmt.where(SessionSnapshot.duration_ms >= min_duration_ms)
        elif min_seconds is not None:
            stmt = stmt.where(SessionSnapshot.time_seconds >= min_seconds)

        total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (
            await db.execute(
                stmt.order_by(SessionSnapshot.collected_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

        return total, [
            SessionItem(
                instance_id=row.instance_id,
                instance_name=row.instance_name,
                db_type=row.db_type,
                session_id=row.session_id,
                serial=row.serial,
                username=row.username,
                host=row.host,
                program=row.program,
                db_name=row.db_name,
                command=row.command,
                state=row.state,
                time_seconds=row.time_seconds,
                duration_ms=row.duration_ms,
                connection_age_ms=row.connection_age_ms,
                state_duration_ms=row.state_duration_ms if row.state_duration_ms is not None else row.duration_ms,
                active_duration_ms=row.active_duration_ms,
                transaction_age_ms=row.transaction_age_ms,
                duration_source=row.duration_source,
                sql_id=row.sql_id,
                sql_text=row.sql_text,
                event=row.event,
                blocking_session=row.blocking_session,
                collected_at=row.collected_at,
                source=row.source,
                collect_error=row.collect_error,
                raw=row.raw or {},
            )
            for row in rows
        ]

    @staticmethod
    async def cleanup_old_snapshots(
        db: AsyncSession,
        retention_days: int = DEFAULT_SESSION_RETENTION_DAYS,
        instance_id: int | None = None,
    ) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        stmt = delete(SessionSnapshot).where(SessionSnapshot.collected_at < cutoff)
        if instance_id is not None:
            stmt = stmt.where(SessionSnapshot.instance_id == instance_id)
        result = await db.execute(stmt)
        return int(result.rowcount or 0)
