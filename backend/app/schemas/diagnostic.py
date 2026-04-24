"""Schemas for session diagnostics."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SessionItem(BaseModel):
    instance_id: int | None = None
    instance_name: str = ""
    db_type: str = ""
    session_id: str = ""
    serial: str = ""
    username: str = ""
    host: str = ""
    program: str = ""
    db_name: str = ""
    command: str = ""
    state: str = ""
    time_seconds: int = 0
    sql_id: str = ""
    sql_text: str = ""
    event: str = ""
    blocking_session: str = ""
    collected_at: datetime | None = None
    source: str = "online"
    collect_error: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class SessionListResponse(BaseModel):
    total: int
    items: list[SessionItem]
    column_list: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)


class SessionHistoryResponse(BaseModel):
    total: int
    items: list[SessionItem]


class KillSessionRequest(BaseModel):
    instance_id: int
    session_id: str
    serial: str = ""
