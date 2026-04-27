"""
在线查询 Pydantic Schema（Sprint 2）。
"""
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class QueryExecuteRequest(BaseModel):
    instance_id: int
    db_name: str
    sql: str = Field(..., min_length=1, max_length=50000)
    limit_num: int = Field(default=100, ge=1, le=100000)
    export_offset: int | None = Field(default=None, ge=0)
    export_limit: int | None = Field(default=None, ge=1, le=100000)

    @field_validator("sql")
    @classmethod
    def sql_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("SQL 不能为空")
        return v.strip()


class QueryResultResponse(BaseModel):
    column_list: list[str]
    rows: list[list[Any]]
    affected_rows: int
    cost_time_ms: int
    is_masked: bool = False
    error: str = ""
    risk_plan: dict | None = None


class QueryLogItem(BaseModel):
    id: int
    user_id: int | None = None
    username: str = ""
    instance_id: int | None = None
    instance_name: str = ""
    db_type: str = ""
    db_name: str
    sqllog: str
    operation_type: str = "execute"
    export_format: str = ""
    effect_row: int
    cost_time_ms: int
    priv_check: bool
    hit_rule: bool = False
    masking: bool
    is_favorite: bool
    client_ip: str = ""
    error: str = ""
    created_at: str

    model_config = {"from_attributes": True}


class QueryLogListResponse(BaseModel):
    total: int
    items: list[QueryLogItem]


# ─── 查询权限申请 ─────────────────────────────────────────────

class PrivApplyRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=50)
    instance_id: int
    group_id: int | None = None
    flow_id: int | None = None
    db_name: str
    table_name: str = ""
    scope_type: Literal["instance", "database", "table"] = "database"
    valid_date: date
    limit_num: int = Field(default=100, ge=1, le=100000)
    priv_type: int = Field(default=1, description="1=库级 2=表级")
    apply_reason: str = Field(default="", max_length=500)
    risk_remark: str = Field(default="", max_length=500)
    audit_auth_groups: str = ""

    @field_validator("valid_date")
    @classmethod
    def valid_date_future(cls, v: date) -> date:
        from datetime import date as d
        if v < d.today():
            raise ValueError("有效期不能早于今天")
        return v

    @model_validator(mode="after")
    def validate_scope_fields(self) -> "PrivApplyRequest":
        self.db_name = self.db_name.strip()
        self.table_name = self.table_name.strip()
        if self.scope_type == "instance":
            self.db_name = ""
            self.table_name = ""
        elif self.scope_type == "database":
            if not self.db_name:
                raise ValueError("库级授权必须填写数据库名")
            self.table_name = ""
        elif self.scope_type == "table":
            if not self.db_name:
                raise ValueError("表级授权必须填写数据库名")
            if not self.table_name:
                raise ValueError("表级授权必须填写表名")
        if self.scope_type == "table" and not self.table_name:
            raise ValueError("表级授权必须填写表名")
        return self


class PrivApplyItem(BaseModel):
    id: int
    title: str
    instance_id: int
    instance_name: str | None = None
    flow_id: int | None = None
    applicant_name: str | None = None
    applicant_username: str | None = None
    db_name: str
    table_name: str
    scope_type: str
    valid_date: str
    limit_num: int
    priv_type: int
    apply_reason: str
    risk_level: str = ""
    risk_summary: str = ""
    risk_remark: str = ""
    status: int
    current_node_name: str | None = None
    approval_progress: str | None = None
    acted_node_name: str | None = None
    acted_action: str | None = None
    acted_at: str | None = None
    can_audit: bool = False
    created_at: str

    model_config = {"from_attributes": True}


class PrivApplyListResponse(BaseModel):
    total: int
    items: list[PrivApplyItem]


class AuditPrivRequest(BaseModel):
    action: str = Field(..., description="pass 或 reject")
    remark: str = ""
    valid_date: date | None = Field(
        default=None,
        description="审批通过时可调整的有效期；只能缩短，不能超过申请有效期",
    )

    @field_validator("action")
    @classmethod
    def action_valid(cls, v: str) -> str:
        if v not in ("pass", "reject"):
            raise ValueError("action 必须是 pass 或 reject")
        return v

    @field_validator("valid_date")
    @classmethod
    def audit_valid_date_future(cls, v: date | None) -> date | None:
        from datetime import date as d
        if v is not None and v < d.today():
            raise ValueError("调整后的有效期不能早于今天")
        return v


class PrivilegeItem(BaseModel):
    id: int
    instance_id: int
    db_name: str
    table_name: str
    scope_type: str
    valid_date: str
    limit_num: int
    priv_type: int
    created_at: str

    model_config = {"from_attributes": True}


class RevokePrivilegeRequest(BaseModel):
    reason: str = Field(default="", max_length=500)
