"""
可观测中心 Pydantic Schema（Sprint 5）。
"""
from datetime import date

from pydantic import BaseModel, Field, field_validator


class MonitorConfigCreate(BaseModel):
    instance_id: int
    exporter_url: str = Field(default="", description="历史字段：Exporter 地址")
    exporter_type: str = Field(default="", description="历史字段：Exporter 类型")
    collect_interval: int = Field(default=60, ge=10, le=3600)
    capacity_collect_interval: int = Field(default=3600, ge=300, le=86400)
    retention_days: int = Field(default=30, ge=1, le=365)
    alert_rules_override: dict = {}

    @field_validator("exporter_url")
    @classmethod
    def url_valid(cls, v: str) -> str:
        if not v:
            return v
        if not v.startswith(("http://", "https://")):
            raise ValueError("exporter_url 必须以 http:// 或 https:// 开头")
        return v


class MonitorConfigUpdate(BaseModel):
    exporter_url: str | None = None
    exporter_type: str | None = None
    collect_interval: int | None = None
    capacity_collect_interval: int | None = None
    retention_days: int | None = None
    is_enabled: bool | None = None
    alert_rules_override: dict | None = None


class MonitorConfigResponse(BaseModel):
    id: int
    instance_id: int
    instance_name: str = ""
    is_enabled: bool
    collect_interval: int
    exporter_url: str
    exporter_type: str
    alert_rules_override: dict
    created_by: str
    capacity_collect_interval: int = 3600
    retention_days: int = 30
    last_metric_collect_at: str | None = None
    last_capacity_collect_at: str | None = None
    last_collect_status: str = "pending"
    last_collect_error: str = ""
    model_config = {"from_attributes": True}


class MonitorPrivApplyRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=50)
    instance_id: int
    group_id: int
    valid_date: date
    apply_reason: str = ""
    audit_auth_groups: str = ""

    @field_validator("valid_date")
    @classmethod
    def future_date(cls, v: date) -> date:
        from datetime import date as d
        if v < d.today():
            raise ValueError("有效期不能早于今天")
        return v


class AuditMonitorPrivRequest(BaseModel):
    action: str = Field(..., description="pass 或 reject")
    remark: str = ""

    @field_validator("action")
    @classmethod
    def action_valid(cls, v: str) -> str:
        if v not in ("pass", "reject"):
            raise ValueError("action 必须是 pass 或 reject")
        return v


class DashboardStats(BaseModel):
    workflow_month_total: int = 0
    workflow_finish_total: int = 0
    workflow_pending_total: int = 0
    instance_total: int = 0
    query_today_total: int = 0
    monitor_instance_total: int = 0


class WorkflowTrendItem(BaseModel):
    date: str
    submit: int
    finish: int
    reject: int


class InstanceDistItem(BaseModel):
    db_type: str
    count: int


class NativeMonitorConfigUpsert(BaseModel):
    is_enabled: bool = True
    collect_interval: int = Field(default=60, ge=10, le=3600)
    capacity_collect_interval: int = Field(default=3600, ge=300, le=86400)
    retention_days: int = Field(default=30, ge=1, le=365)


class MonitorSnapshotResponse(BaseModel):
    instance_id: int
    collected_at: str | None = None
    status: str = "not_configured"
    error: str = ""
    missing_groups: dict = {}
    is_up: bool = False
    version: str = ""
    uptime_seconds: int | None = None
    current_connections: int | None = None
    active_sessions: int | None = None
    max_connections: int | None = None
    connection_usage: float | None = None
    qps: float | None = None
    tps: float | None = None
    slow_queries: int | None = None
    error_count: int | None = None
    lock_waits: int | None = None
    long_transactions: int | None = None
    replication_lag_seconds: int | None = None
    total_size_bytes: int | None = None
    extra_metrics: dict = {}


class MonitorListItem(BaseModel):
    instance_id: int
    instance_name: str
    db_type: str
    is_active: bool
    config_id: int | None = None
    config_enabled: bool = False
    collect_interval: int | None = None
    capacity_collect_interval: int | None = None
    retention_days: int | None = None
    last_metric_collect_at: str | None = None
    last_capacity_collect_at: str | None = None
    last_collect_status: str = "not_configured"
    last_collect_error: str = ""
    latest: MonitorSnapshotResponse | None = None


class MonitorTrendPoint(BaseModel):
    collected_at: str
    current_connections: int | None = None
    qps: float | None = None
    tps: float | None = None
    slow_queries: int | None = None
    total_size_bytes: int | None = None


class MonitorDatabaseCapacityItem(BaseModel):
    db_name: str
    collected_at: str
    table_count: int
    data_size_bytes: int
    index_size_bytes: int
    total_size_bytes: int
    row_count: int
    status: str = "success"
    error: str = ""


class MonitorTableCapacityItem(BaseModel):
    db_name: str
    table_name: str
    collected_at: str
    data_size_bytes: int
    index_size_bytes: int
    total_size_bytes: int
    row_count: int
    extra: dict = {}
