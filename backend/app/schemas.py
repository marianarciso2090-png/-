from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models import ResearchStatus


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=512)


class ResearchCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32, description="A 股代码或简称")
    as_of: date | None = Field(default=None, description="研究截至日；留空则使用最新可得数据")

    @field_validator("symbol")
    @classmethod
    def clean_symbol(cls, value: str) -> str:
        value = " ".join(value.strip().split())
        if not value:
            raise ValueError("股票代码或简称不能为空")
        return value


class ResearchSummary(BaseModel):
    id: str
    symbol: str
    resolved_name: str | None
    as_of_date: date | None
    status: ResearchStatus
    created_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None

    model_config = {"from_attributes": True}


class EvidenceOut(BaseModel):
    id: str
    source_server: str
    tool_name: str
    request_params: dict
    response_sha256: str
    excerpt: str
    captured_at: datetime | None

    model_config = {"from_attributes": True}


class ResearchDetail(ResearchSummary):
    report_markdown: str | None
    evidence: list[EvidenceOut]


class ResearchPlan(BaseModel):
    focus: list[str] = Field(min_length=3, max_length=6)
    selected_groups: list[
        Literal["company", "financials", "market", "ownership", "risk", "events", "esg", "notices", "news"]
    ] = Field(default_factory=list)


class ReportClaim(BaseModel):
    statement: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(min_length=1)
    kind: Literal["fact", "inference", "data_gap"]


class ReportDraft(BaseModel):
    title: str
    executive_summary: list[ReportClaim]
    company_and_business: list[ReportClaim]
    industry_and_peers: list[ReportClaim]
    financial_quality: list[ReportClaim]
    valuation_and_scenarios: list[ReportClaim]
    catalysts_and_risks: list[ReportClaim]
    data_gaps: list[ReportClaim]
