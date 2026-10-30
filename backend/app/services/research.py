from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from redis import Redis
from sqlalchemy import select

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import EvidenceSnapshot, ResearchRun, ResearchStatus
from app.schemas import ReportClaim, ReportDraft, ResearchPlan
from app.services.deepseek import DeepSeekClient, DeepSeekError
from app.services.analytics import calculate_financial_indicators
from app.services.ifind import (
    CollectedPayload,
    IFindClient,
    IFindError,
    default_collection_specs,
    payload_excerpt,
    payload_hash,
)
from app.services.renderer import render_markdown


def _redis_client() -> Redis | None:
    if get_settings().app_env == "local":
        return None
    try:
        return Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=2)
    except Exception:
        return None


def _set_status(run: ResearchRun, status: ResearchStatus) -> None:
    run.status = status


def _add_evidence(db, research_id: str, collected: CollectedPayload) -> EvidenceSnapshot:
    item = EvidenceSnapshot(
        research_id=research_id,
        source_server=collected.server,
        tool_name=collected.tool,
        request_params=collected.params,
        response_sha256=payload_hash(collected.payload),
        raw_payload=collected.payload,
        excerpt=payload_excerpt(collected.payload),
    )
    db.add(item)
    db.flush()
    return item


def _add_collection_failure(db, research_id: str, server: str, tool: str, params: dict, message: str) -> EvidenceSnapshot:
    payload = {"collection_error": message}
    item = EvidenceSnapshot(
        research_id=research_id,
        source_server=server,
        tool_name=f"failed:{tool}",
        request_params=params,
        response_sha256=payload_hash(payload),
        raw_payload=payload,
        excerpt="该 iFinD 数据项未采集成功：" + message,
    )
    db.add(item)
    db.flush()
    return item


def _add_derived_metrics(db, research_id: str, source_items: list[EvidenceSnapshot]) -> EvidenceSnapshot | None:
    metrics = calculate_financial_indicators([(item.id, item.raw_payload) for item in source_items])
    if not metrics:
        return None
    payload = {"metrics": metrics, "method": "only numeric fields in structured iFinD records are used"}
    item = EvidenceSnapshot(
        research_id=research_id,
        source_server="derived",
        tool_name="financial_calculations",
        request_params={"source_evidence_ids": [source.id for source in source_items]},
        response_sha256=payload_hash(payload),
        raw_payload=payload,
        excerpt=payload_excerpt(payload),
    )
    db.add(item)
    db.flush()
    return item


def _evidence_catalog(items: Iterable[EvidenceSnapshot]) -> list[dict]:
    return [
        {
            "id": item.id,
            "source": f"iFinD {item.source_server}/{item.tool_name}",
            "request": item.request_params,
            "excerpt": item.excerpt,
            "captured_at": item.captured_at.isoformat() if item.captured_at else None,
        }
        for item in items
        if not item.tool_name.startswith("failed:")
    ]


def _fallback_draft(symbol: str, evidence: list[EvidenceSnapshot], collection_errors: list[EvidenceSnapshot]) -> ReportDraft:
    def first_matching(keyword: str) -> str | None:
        for item in evidence:
            if keyword in item.tool_name:
                return item.id
        return None

    generic = evidence[0].id if evidence else (collection_errors[0].id if collection_errors else "unavailable")

    def claim(label: str, tool_keyword: str, kind: str = "fact") -> list[ReportClaim]:
        evidence_id = first_matching(tool_keyword) or generic
        return [ReportClaim(statement=f"已采集{label}，请结合证据附录核验具体口径。", evidence_ids=[evidence_id], kind=kind)]

    gaps = [
        ReportClaim(
            statement="模型服务不可用时仅生成证据导览，未作自动分析或估值结论。",
            evidence_ids=[generic],
            kind="data_gap",
        )
    ]
    for item in collection_errors:
        gaps.append(ReportClaim(statement=item.excerpt, evidence_ids=[item.id], kind="data_gap"))
    return ReportDraft(
        title=f"{symbol} 个股研究报告（证据导览）",
        executive_summary=claim("公司、财务与市场数据", "get_stock_info"),
        company_and_business=claim("公司资料与主营业务", "get_stock_info"),
        industry_and_peers=[
            ReportClaim(
                statement="当前自动流程未在没有模型核验时生成可比公司名单，以避免虚构相似性判断。",
                evidence_ids=[generic],
                kind="data_gap",
            )
        ],
        financial_quality=claim("财务质量相关数据", "get_stock_financials"),
        valuation_and_scenarios=[
            ReportClaim(
                statement="未在缺少模型核验时生成估值情景；请先核验 PE/PB/PS 与可比公司口径。",
                evidence_ids=[first_matching("get_stock_performance") or generic],
                kind="data_gap",
            )
        ],
        catalysts_and_risks=claim("风险、事件与公告资料", "get_risk_indicators"),
        data_gaps=gaps,
    )


def _guard_draft(draft: ReportDraft, valid_ids: set[str], fallback_id: str) -> ReportDraft:
    """Remove any model-created citation IDs before the report reaches the user."""
    moved_to_gaps: list[ReportClaim] = []
    for field_name in (
        "executive_summary",
        "company_and_business",
        "industry_and_peers",
        "financial_quality",
        "valuation_and_scenarios",
        "catalysts_and_risks",
        "data_gaps",
    ):
        guarded: list[ReportClaim] = []
        for claim in getattr(draft, field_name):
            ids = [evidence_id for evidence_id in claim.evidence_ids if evidence_id in valid_ids]
            if ids:
                guarded.append(claim.model_copy(update={"evidence_ids": ids}))
            else:
                gap = ReportClaim(
                    statement="该段缺少可验证的 iFinD 证据，已移入数据缺口。",
                    evidence_ids=[fallback_id],
                    kind="data_gap",
                )
                if field_name == "data_gaps":
                    guarded.append(gap)
                else:
                    moved_to_gaps.append(gap)
        setattr(draft, field_name, guarded)
    draft.data_gaps.extend(moved_to_gaps)
    return draft


def run_research(research_id: str) -> None:
    """Run a complete job. This function is intentionally independent of Celery for testability."""
    settings = get_settings()
    db = SessionLocal()
    client: IFindClient | None = None
    model: DeepSeekClient | None = None
    try:
        run = db.scalar(select(ResearchRun).where(ResearchRun.id == research_id))
        if not run:
            return
        _set_status(run, ResearchStatus.COLLECTING)
        db.commit()

        try:
            model = DeepSeekClient(settings)
            plan = model.create_plan(run.symbol, run.as_of_date.isoformat() if run.as_of_date else None)
        except DeepSeekError:
            # A source-backed fallback report is safer than inventing an analysis.
            plan = ResearchPlan(focus=["公司资料", "财务质量", "估值口径与风险"])
        run.plan_json = plan.model_dump(mode="json")
        db.commit()

        client = IFindClient(settings, _redis_client())
        successful: list[EvidenceSnapshot] = []
        failures: list[EvidenceSnapshot] = []
        for server, tool, params in default_collection_specs(
            run.symbol, run.as_of_date.isoformat() if run.as_of_date else None
        ):
            try:
                successful.append(_add_evidence(db, run.id, client.call(server, tool, params)))
            except IFindError as exc:
                failures.append(_add_collection_failure(db, run.id, server, tool, params, str(exc)))
            db.commit()

        if not successful:
            raise IFindError("所有 iFinD 数据请求均失败，请检查密钥、权限、网络或标的代码")

        derived = _add_derived_metrics(db, run.id, successful)
        if derived:
            successful.append(derived)
            db.commit()

        _set_status(run, ResearchStatus.ANALYSING)
        db.commit()
        fallback = _fallback_draft(run.symbol, successful, failures)
        try:
            if model is None:
                model = DeepSeekClient(settings)
            draft = model.write_report(
                symbol=run.symbol,
                as_of=run.as_of_date.isoformat() if run.as_of_date else None,
                plan=plan,
                evidence=_evidence_catalog(successful),
            )
        except DeepSeekError:
            draft = fallback

        valid_ids = {item.id for item in successful}
        draft = _guard_draft(draft, valid_ids, successful[0].id)
        _set_status(run, ResearchStatus.REVIEWING)
        db.commit()

        # Exactly one model-powered repair pass. Validation still runs when it is unavailable.
        try:
            if model is None:
                model = DeepSeekClient(settings)
            draft = model.review_report(draft=draft, valid_evidence_ids=sorted(valid_ids))
            draft = _guard_draft(draft, valid_ids, successful[0].id)
        except DeepSeekError:
            pass

        run.report_json = draft.model_dump(mode="json")
        run.report_markdown = render_markdown(
            symbol=run.symbol,
            resolved_name=run.resolved_name,
            as_of=run.as_of_date,
            draft=draft,
            evidence=[*successful, *failures],
        )
        run.status = ResearchStatus.COMPLETED
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        run = db.scalar(select(ResearchRun).where(ResearchRun.id == research_id))
        if run:
            run.status = ResearchStatus.FAILED
            run.error_code = "RESEARCH_FAILED"
            # Do not persist arbitrary exception text: HTTP libraries and drivers may
            # include endpoint or credential-shaped diagnostic details.
            if isinstance(exc, (IFindError, DeepSeekError)):
                run.error_message = str(exc)[:500]
            else:
                run.error_message = "研究任务遇到内部错误，请检查服务日志和配置"
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        if client:
            client.close()
        if model:
            model.close()
        db.close()
