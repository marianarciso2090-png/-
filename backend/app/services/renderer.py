from __future__ import annotations

from datetime import date

from app.models import EvidenceSnapshot
from app.schemas import ReportClaim, ReportDraft

DISCLAIMER = "仅供研究参考，不构成投资建议。报告不包含买入、持有或卖出指令。"


def _claim_line(claim: ReportClaim) -> str:
    prefix = {"fact": "", "inference": "分析性推断：", "data_gap": "数据缺口："}[claim.kind]
    citations = " ".join(f"[证据:{item}]" for item in claim.evidence_ids)
    return f"- {prefix}{claim.statement} {citations}".rstrip()


def render_markdown(
    *, symbol: str, resolved_name: str | None, as_of: date | None, draft: ReportDraft, evidence: list[EvidenceSnapshot]
) -> str:
    display_name = resolved_name or symbol
    sections = [
        ("结论摘要", draft.executive_summary),
        ("公司与商业模式", draft.company_and_business),
        ("行业与可比公司", draft.industry_and_peers),
        ("财务质量", draft.financial_quality),
        ("估值与情景分析", draft.valuation_and_scenarios),
        ("催化剂与风险", draft.catalysts_and_risks),
        ("数据缺口", draft.data_gaps),
    ]
    lines = [
        f"# {draft.title or f'{display_name}个股研究报告'}",
        "",
        f"- 标的：{display_name}（输入：{symbol}）",
        f"- 数据截至：{as_of.isoformat() if as_of else '最新可得数据'}",
        f"- {DISCLAIMER}",
        "",
    ]
    for title, claims in sections:
        lines.extend([f"## {title}", ""])
        lines.extend(_claim_line(claim) for claim in claims)
        lines.append("")

    lines.extend(["## 证据附录", ""])
    for item in evidence:
        captured = item.captured_at.isoformat() if item.captured_at else "处理中"
        lines.extend(
            [
                f"### 证据:{item.id}",
                f"- 来源：{'系统计算（源 iFinD 证据）' if item.source_server == 'derived' else f'iFinD `{item.source_server}/{item.tool_name}`'}",
                f"- 采集时间：{captured}",
                f"- 请求：`{item.request_params}`",
                f"- 响应 SHA-256：`{item.response_sha256}`",
                f"- 摘要：{item.excerpt}",
                "",
            ]
        )
    return "\n".join(lines)
