"""Risk plan schemas."""

from typing import Literal

from pydantic import BaseModel, Field

RiskScope = Literal["workflow", "query_privilege", "archive"]
RiskLevel = Literal["low", "medium", "high"]


class RiskPlan(BaseModel):
    scope: RiskScope
    level: RiskLevel = "low"
    summary: str = ""
    risks: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    requires_manual_remark: bool = False
