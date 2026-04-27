"""
SQL 工单 Pydantic Schema（Sprint 3）。
"""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class WorkflowCreateRequest(BaseModel):
    workflow_name: str = Field(..., min_length=1, max_length=50)
    group_id: int | None = None
    instance_id: int
    db_name: str
    sql_content: str = Field(..., min_length=1)
    syntax_type: int = Field(default=0, description="0未知 1DDL 2DML 3导出")
    is_backup: bool = True
    run_date_start: datetime | None = None
    run_date_end: datetime | None = None
    # 多级审批流：指定流程模板 ID；不传则使用资源组默认单级审批
    flow_id: int | None = Field(default=None, description="审批流模板 ID（不传则使用默认单级审批）")
    risk_remark: str = Field(default="", max_length=500, description="高风险变更说明/回滚说明")

    @field_validator("sql_content")
    @classmethod
    def sql_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("SQL 内容不能为空")
        return v


class WorkflowAuditRequest(BaseModel):
    action: str = Field(..., description="pass 或 reject")
    remark: str = Field(default="", max_length=500)

    @field_validator("action")
    @classmethod
    def action_valid(cls, v: str) -> str:
        if v not in ("pass", "reject"):
            raise ValueError("action 必须是 pass 或 reject")
        return v


class WorkflowExecuteRequest(BaseModel):
    mode: str = Field(default="immediate", description="immediate=立即执行 scheduled=定时执行 external=外部已执行")
    scheduled_at: datetime | None = Field(default=None, description="预约平台执行时间")
    timing_time: datetime | None = Field(default=None, description="兼容旧字段：预约平台执行时间")
    external_executed_at: datetime | None = Field(default=None, description="外部实际执行时间")
    external_status: str | None = Field(default=None, description="success 或 failed")
    external_remark: str | None = Field(default=None, max_length=500, description="外部执行结果备注")

    @field_validator("mode")
    @classmethod
    def mode_valid(cls, v: str) -> str:
        aliases = {"auto": "immediate", "manual": "external", "timing": "scheduled"}
        normalized = aliases.get(v, v)
        if normalized not in ("immediate", "scheduled", "external"):
            raise ValueError("mode 必须是 immediate、scheduled 或 external")
        return normalized

    @field_validator("external_status")
    @classmethod
    def external_status_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in ("success", "failed"):
            raise ValueError("external_status 必须是 success 或 failed")
        return v


class WorkflowItem(BaseModel):
    id: int
    workflow_name: str
    group_name: str
    instance_id: int
    db_name: str
    syntax_type: int
    is_backup: bool
    engineer: str
    engineer_display: str
    status: int
    status_desc: str
    audit_auth_groups: str
    run_date_start: str | None
    run_date_end: str | None
    finish_time: str | None
    execute_mode: str | None = None
    scheduled_execute_at: str | None = None
    executed_by_id: int | None = None
    executed_by_name: str | None = None
    external_executed_at: str | None = None
    external_result_status: str | None = None
    external_result_remark: str | None = None
    created_at: str

    model_config = {"from_attributes": True}


class WorkflowDetailResponse(BaseModel):
    id: int
    workflow_name: str
    group_id: int
    group_name: str
    instance_id: int
    db_name: str
    syntax_type: int
    is_backup: bool
    engineer: str
    engineer_display: str
    status: int
    status_desc: str
    audit_auth_groups: str
    run_date_start: str | None
    run_date_end: str | None
    finish_time: str | None
    execute_mode: str | None = None
    scheduled_execute_at: str | None = None
    executed_by_id: int | None = None
    executed_by_name: str | None = None
    external_executed_at: str | None = None
    external_result_status: str | None = None
    external_result_remark: str | None = None
    created_at: str
    sql_content: str = ""
    review_content: str = ""
    execute_result: str = ""
    risk_plan: dict | None = None
    risk_remark: str = ""
    audit_logs: list[dict] = []


class WorkflowListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[WorkflowItem]


class WorkflowCheckRequest(BaseModel):
    instance_id: int
    db_name: str
    sql_content: str
