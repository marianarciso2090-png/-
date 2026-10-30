from datetime import datetime, timezone

from app.models import EvidenceSnapshot
from app.schemas import ReportClaim, ReportDraft
from app.services.renderer import render_markdown
from app.services.research import _guard_draft


def _draft(evidence_id: str) -> ReportDraft:
    claim = ReportClaim(statement="可验证事实", evidence_ids=[evidence_id], kind="fact")
    return ReportDraft(
        title="测试报告",
        executive_summary=[claim],
        company_and_business=[claim],
        industry_and_peers=[claim],
        financial_quality=[claim],
        valuation_and_scenarios=[claim],
        catalysts_and_risks=[claim],
        data_gaps=[claim],
    )


def test_guard_replaces_hallucinated_citation() -> None:
    draft = _guard_draft(_draft("invented"), {"known"}, "known")
    assert draft.executive_summary == []
    assert draft.data_gaps[-1].kind == "data_gap"
    assert draft.data_gaps[-1].evidence_ids == ["known"]


def test_markdown_always_carries_disclaimer_and_evidence() -> None:
    evidence = EvidenceSnapshot(
        id="known",
        research_id="run",
        source_server="stock",
        tool_name="get_stock_info",
        request_params={"query": "测试"},
        response_sha256="a" * 64,
        raw_payload={"value": 1},
        excerpt="测试资料",
        captured_at=datetime.now(timezone.utc),
    )
    output = render_markdown(symbol="600519", resolved_name=None, as_of=None, draft=_draft("known"), evidence=[evidence])
    assert "不构成投资建议" in output
    assert "证据:known" in output
