"""SQL analysis schemas backed by slow query samples."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SlowQueryLogItem(BaseModel):
    id: int
    source: str
    instance_id: int | None = None
    instance_name: str = ""
    db_type: str = ""
    db_name: str = ""
    sql_text: str
    sql_fingerprint: str
    fingerprint_text: str = ""
    duration_ms: int = 0
    rows_examined: int = 0
    rows_sent: int = 0
    username: str = ""
    client_host: str = ""
    occurred_at: datetime
    analysis_tags: list[str] = Field(default_factory=list)
    collect_error: str = ""

    model_config = {"from_attributes": True}


class SlowQueryLogListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[SlowQueryLogItem]


class SlowQueryTrendPoint(BaseModel):
    bucket: str
    count: int = 0
    avg_duration_ms: int = 0
    failed_count: int = 0


class SlowQueryOverviewResponse(BaseModel):
    total: int = 0
    fingerprint_count: int = 0
    instance_count: int = 0
    failed_count: int = 0
    avg_duration_ms: int = 0
    p95_duration_ms: int = 0
    max_duration_ms: int = 0
    slowest: SlowQueryLogItem | None = None
    unsupported_msg: str = ""
    trends: list[SlowQueryTrendPoint] = Field(default_factory=list)
    source_distribution: list[SlowQueryDistributionItem] = Field(default_factory=list)


class SlowQueryFingerprintItem(BaseModel):
    sql_fingerprint: str
    fingerprint_text: str
    sample_sql: str
    count: int
    avg_duration_ms: int
    max_duration_ms: int
    p95_duration_ms: int
    rows_examined: int
    rows_sent: int
    analysis_tags: list[str] = Field(default_factory=list)
    last_seen_at: datetime | None = None


class SlowQueryFingerprintListResponse(BaseModel):
    total: int
    items: list[SlowQueryFingerprintItem]


class SlowQueryDistributionItem(BaseModel):
    name: str
    count: int
    avg_duration_ms: int = 0


class SlowQueryRecommendation(BaseModel):
    severity: str
    title: str
    detail: str


class SlowQueryFingerprintDetailResponse(BaseModel):
    fingerprint: SlowQueryFingerprintItem
    trends: list[SlowQueryTrendPoint] = Field(default_factory=list)
    instance_distribution: list[SlowQueryDistributionItem] = Field(default_factory=list)
    database_distribution: list[SlowQueryDistributionItem] = Field(default_factory=list)
    user_distribution: list[SlowQueryDistributionItem] = Field(default_factory=list)
    source_distribution: list[SlowQueryDistributionItem] = Field(default_factory=list)
    recommendations: list[SlowQueryRecommendation] = Field(default_factory=list)
    samples: list[SlowQueryLogItem] = Field(default_factory=list)


class SlowQueryCollectResponse(BaseModel):
    instances: int = 0
    saved: int = 0
    failed: int = 0
    unsupported: int = 0
    msg: str = ""
    errors: list[str] = Field(default_factory=list)


class SlowQueryConfigUpsert(BaseModel):
    instance_id: int
    is_enabled: bool = True
    threshold_ms: int = Field(default=1000, ge=0, le=3600000)
    collect_interval: int = Field(default=300, ge=30, le=86400)
    retention_days: int = Field(default=30, ge=1, le=365)
    collect_limit: int = Field(default=100, ge=1, le=1000)


class SlowQueryConfigUpdate(BaseModel):
    is_enabled: bool | None = None
    threshold_ms: int | None = Field(default=None, ge=0, le=3600000)
    collect_interval: int | None = Field(default=None, ge=30, le=86400)
    retention_days: int | None = Field(default=None, ge=1, le=365)
    collect_limit: int | None = Field(default=None, ge=1, le=1000)


class SlowQueryConfigItem(BaseModel):
    id: int
    instance_id: int
    instance_name: str = ""
    db_type: str = ""
    is_enabled: bool
    threshold_ms: int
    collect_interval: int
    retention_days: int
    collect_limit: int
    last_collect_at: datetime | None = None
    last_collect_status: str = "never"
    last_collect_error: str = ""
    last_collect_count: int = 0
    created_by: str = ""

    model_config = {"from_attributes": True}


class SlowQueryConfigListResponse(BaseModel):
    total: int
    items: list[SlowQueryConfigItem]


class SlowQueryExplainRequest(BaseModel):
    log_id: int | None = None
    instance_id: int | None = None
    db_name: str = ""
    sql: str = ""


class SlowQueryExplainResponse(BaseModel):
    supported: bool = False
    db_type: str = ""
    summary: list[SlowQueryRecommendation] = Field(default_factory=list)
    plan: dict[str, Any] = Field(default_factory=dict)
    raw: Any = None
    msg: str = ""


class SlowQueryEngineRow(BaseModel):
    source: str
    db_name: str = ""
    sql_text: str
    duration_ms: int = 0
    rows_examined: int = 0
    rows_sent: int = 0
    username: str = ""
    client_host: str = ""
    occurred_at: datetime | None = None
    source_ref: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)
