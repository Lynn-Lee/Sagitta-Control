"""Schemas for session diagnostics."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class SessionCollectConfigUpsert(BaseModel):
    instance_id: int
    is_enabled: bool = True
    collect_interval: int = Field(default=60, ge=10, le=86400)
    retention_days: int = Field(default=30, ge=1, le=365)


class SessionCollectConfigUpdate(BaseModel):
    is_enabled: bool | None = None
    collect_interval: int | None = Field(default=None, ge=10, le=86400)
    retention_days: int | None = Field(default=None, ge=1, le=365)


class SessionCollectConfigItem(BaseModel):
    id: int
    instance_id: int
    instance_name: str = ""
    db_type: str = ""
    is_enabled: bool
    collect_interval: int
    retention_days: int
    last_collect_at: datetime | None = None
    last_collect_status: str
    last_collect_error: str = ""
    last_collect_count: int
    created_by: str = ""

    model_config = ConfigDict(from_attributes=True)


class SessionCollectConfigListResponse(BaseModel):
    total: int
    items: list[SessionCollectConfigItem]
