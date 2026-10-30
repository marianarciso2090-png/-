from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import COOKIE_NAME, clear_session, create_session, require_session
from app.db import create_schema, get_db
from app.models import CredentialSession, ResearchRun, ResearchStatus
from app.schemas import KeyConnectRequest, ResearchCreate, ResearchDetail, ResearchSummary
from app.worker import run_research_task

settings = get_settings()
local_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research-local") if settings.app_env == "local" else None


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_schema()
    yield


app = FastAPI(
    title="A 股个股研究智能体",
    version="0.1.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(RequestValidationError)
async def invalid_input(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Framework validation errors otherwise echo the submitted secret in `input`.
    return JSONResponse(status_code=422, content={"detail": "输入格式有误，请检查必填项、密钥和日期。"})


@app.post("/session", status_code=status.HTTP_204_NO_CONTENT)
def connect_keys(payload: KeyConnectRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    create_session(response, db, settings, payload.ifind_mcp_api_key.get_secret_value(),
        payload.deepseek_api_key.get_secret_value(), request.cookies.get(COOKIE_NAME))


@app.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_keys(response: Response, db: Session = Depends(get_db), session: CredentialSession = Depends(require_session)) -> None:
    db.delete(session)
    db.commit()
    clear_session(response)


@app.get("/session")
def current_session(_: CredentialSession = Depends(require_session)) -> dict[str, bool]:
    return {"connected": True}


@app.get("/integrations")
def integrations(_: CredentialSession = Depends(require_session)) -> dict[str, dict[str, bool]]:
    """Both keys are explicitly supplied by this session, never by host defaults."""
    return {
        "ifind": {"configured": True},
        "deepseek": {"configured": True},
    }


@app.post("/researches", response_model=ResearchSummary, status_code=status.HTTP_202_ACCEPTED)
def create_research(
    payload: ResearchCreate,
    db: Session = Depends(get_db),
    session: CredentialSession = Depends(require_session),
) -> ResearchRun:
    if payload.as_of and payload.as_of > datetime.now(ZoneInfo("Asia/Shanghai")).date():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="截至日期不能晚于今天")
    run = ResearchRun(symbol=payload.symbol, as_of_date=payload.as_of, status=ResearchStatus.QUEUED, owner_id=session.owner_id)
    db.add(run)
    db.commit()
    db.refresh(run)
    try:
        if local_executor is not None:
            from app.services.research import run_research

            local_executor.submit(run_research, run.id, session.id)
        else:
            run_research_task.delay(run.id, session.id)
    except Exception:
        run.status = ResearchStatus.FAILED
        run.error_code = "QUEUE_UNAVAILABLE"
        run.error_message = "任务无法启动，请检查服务配置后重新创建任务"
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="研究任务暂时无法启动，请稍后重试") from None
    return run


@app.get("/researches", response_model=list[ResearchSummary])
def list_researches(
    symbol: str | None = Query(default=None, max_length=32),
    as_of: date | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    session: CredentialSession = Depends(require_session),
) -> list[ResearchRun]:
    stmt = select(ResearchRun).where(ResearchRun.owner_id == session.owner_id).order_by(ResearchRun.created_at.desc()).limit(limit)
    if symbol:
        stmt = stmt.where(ResearchRun.symbol.ilike(f"%{symbol.strip()}%"))
    if as_of:
        stmt = stmt.where(ResearchRun.as_of_date == as_of)
    return list(db.scalars(stmt))


def _get_research_or_404(research_id: str, db: Session, owner_id: str) -> ResearchRun:
    stmt = select(ResearchRun).options(selectinload(ResearchRun.evidence)).where(ResearchRun.id == research_id, ResearchRun.owner_id == owner_id)
    run = db.scalar(stmt)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该研究报告")
    return run


@app.get("/researches/{research_id}", response_model=ResearchDetail)
def get_research(research_id: str, db: Session = Depends(get_db), session: CredentialSession = Depends(require_session)) -> ResearchRun:
    return _get_research_or_404(research_id, db, session.owner_id)


@app.get("/researches/{research_id}/markdown")
def download_markdown(research_id: str, db: Session = Depends(get_db), session: CredentialSession = Depends(require_session)) -> PlainTextResponse:
    run = _get_research_or_404(research_id, db, session.owner_id)
    if not run.report_markdown:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="报告尚未生成")
    filename = f"research-{run.symbol}-{research_id[:8]}.md"
    return PlainTextResponse(
        run.report_markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=\"research-{research_id[:8]}.md\"; filename*=UTF-8''{quote(filename, safe='')}"},
    )
