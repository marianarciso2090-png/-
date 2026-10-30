from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

import app.db as db_module
from app.db import Base
from app.models import ResearchRun, ResearchStatus
from app.models import CredentialSession
from app.core.config import get_settings
from app.core.security import create_session
from fastapi import Response
from app.schemas import ReportClaim, ReportDraft, ResearchPlan
from app.services.ifind import CollectedPayload
import app.services.research as research_module


class FakeIFindClient:
    def __init__(self, settings, *_args, **_kwargs) -> None:
        assert settings.ifind_mcp_api_key.get_secret_value() == "submitted-ifind"

    def call(self, server: str, tool: str, params: dict) -> CollectedPayload:
        payload = {"tool": tool, "query": params["query"]}
        if tool == "get_stock_financials":
            payload["rows"] = [
                {"year": "2024", "revenue": 100, "net_profit": 10},
                {"year": "2025", "revenue": 120, "net_profit": 18, "operating_cash_flow": 20, "total_assets": 200, "total_liabilities": 80},
            ]
        return CollectedPayload(server, tool, params, payload, False)

    def close(self) -> None:
        pass


class FakeDeepSeekClient:
    def __init__(self, settings, *_args, **_kwargs) -> None:
        assert settings.deepseek_api_key.get_secret_value() == "submitted-deepseek"

    def create_plan(self, *_args, **_kwargs) -> ResearchPlan:
        return ResearchPlan(focus=["业务护城河", "财务质量", "估值与风险"])

    def write_report(self, *, evidence: list[dict], **_kwargs) -> ReportDraft:
        evidence_id = evidence[0]["id"]
        claim = ReportClaim(statement="模型仅使用已提供的模拟 iFinD 证据。", evidence_ids=[evidence_id], kind="fact")
        return ReportDraft(
            title="模拟报告",
            executive_summary=[claim], company_and_business=[claim], industry_and_peers=[claim],
            financial_quality=[claim], valuation_and_scenarios=[claim], catalysts_and_risks=[claim], data_gaps=[],
        )

    def review_report(self, *, draft: ReportDraft, **_kwargs) -> ReportDraft:
        return draft

    def close(self) -> None:
        pass


def test_full_research_pipeline_with_mocked_providers(monkeypatch) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db_module.engine = engine
    db_module.SessionLocal.configure(bind=engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(research_module, "IFindClient", FakeIFindClient)
    monkeypatch.setattr(research_module, "DeepSeekClient", FakeDeepSeekClient)

    db = db_module.SessionLocal()
    create_session(Response(), db, get_settings(), "submitted-ifind", "submitted-deepseek", None)
    credential = db.scalar(select(CredentialSession))
    run = ResearchRun(symbol="600519", status=ResearchStatus.QUEUED, owner_id=credential.owner_id)
    db.add(run); db.commit(); db.refresh(run)
    research_module.run_research(run.id, credential.id)
    db.expire_all()
    result = db.scalar(select(ResearchRun).where(ResearchRun.id == run.id))

    assert result is not None
    assert result.status == ResearchStatus.COMPLETED
    assert result.report_markdown is not None and "不构成投资建议" in result.report_markdown
    assert len(result.evidence) == 11  # Ten provider calls plus a derived-metrics evidence snapshot.
    assert any(item.tool_name == "financial_calculations" for item in result.evidence)
    db.close()
