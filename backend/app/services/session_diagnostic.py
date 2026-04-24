"""Session diagnostics and history helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.models import ResultSet
from app.models.instance import Instance
from app.models.session import SessionSnapshot
from app.schemas.diagnostic import SessionItem


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
    item.time_seconds = _int(_pick(raw, "time_seconds", "seconds", "time", "last_call_et", "secs_running", "elapsed_sec", "elapsed"))
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


class SessionDiagnosticService:
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
        sql_keyword: str | None = None,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
        min_seconds: int | None = None,
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
        if sql_keyword:
            stmt = stmt.where(SessionSnapshot.sql_text.ilike(f"%{sql_keyword}%"))
        if date_start:
            stmt = stmt.where(SessionSnapshot.collected_at >= date_start)
        if date_end:
            stmt = stmt.where(SessionSnapshot.collected_at <= date_end)
        if min_seconds is not None:
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
    async def cleanup_old_snapshots(db: AsyncSession, retention_days: int = 30) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        result = await db.execute(delete(SessionSnapshot).where(SessionSnapshot.collected_at < cutoff))
        return int(result.rowcount or 0)
