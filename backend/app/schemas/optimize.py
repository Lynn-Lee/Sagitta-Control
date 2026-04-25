"""SQL optimization v2 schemas."""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

SupportLevel = Literal["full", "partial", "static_only", "unsupported"]
OptimizeSource = Literal["manual", "slowlog", "fingerprint"]


class OptimizeAnalyzeRequest(BaseModel):
    """Unified SQL optimization analysis request."""

    log_id: int | None = None
    fingerprint: str | None = None
    instance_id: int | None = None
    db_name: str = ""
    sql: str = ""

    @model_validator(mode="after")
    def validate_source(self) -> "OptimizeAnalyzeRequest":
        if self.log_id or self.fingerprint:
            return self
        if not self.instance_id or not self.sql.strip():
            raise ValueError("必须提供 log_id、fingerprint，或 instance_id + sql")
        return self


class OptimizeFinding(BaseModel):
    severity: Literal["critical", "warning", "info", "ok"] = "info"
    code: str
    title: str
    detail: str
    evidence: str = ""
    confidence: float = Field(default=0.7, ge=0, le=1)


class OptimizeRecommendation(BaseModel):
    priority: int = Field(default=99, ge=1)
    type: str = "general"
    title: str
    action: str
    reason: str = ""
    risk: str = ""
    confidence: float = Field(default=0.7, ge=0, le=1)


class OptimizePlan(BaseModel):
    format: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    operators: list[dict[str, Any]] = Field(default_factory=list)


class OptimizeMetadata(BaseModel):
    tables: list[str] = Field(default_factory=list)
    indexes: list[dict[str, Any]] = Field(default_factory=list)
    statistics: list[dict[str, Any]] = Field(default_factory=list)
    slowlog: dict[str, Any] = Field(default_factory=dict)


class OptimizeAnalyzeResponse(BaseModel):
    supported: bool = True
    support_level: SupportLevel = "static_only"
    engine: str = ""
    source: OptimizeSource = "manual"
    risk_score: int = Field(default=0, ge=0, le=100)
    summary: str = ""
    findings: list[OptimizeFinding] = Field(default_factory=list)
    recommendations: list[OptimizeRecommendation] = Field(default_factory=list)
    plan: OptimizePlan = Field(default_factory=OptimizePlan)
    metadata: OptimizeMetadata = Field(default_factory=OptimizeMetadata)
    raw: Any = None
    sql: str = ""
    msg: str = ""

