from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import authenticate, clear_session, require_admin, set_session
from app.db import create_schema, get_db
from app.models import ResearchRun, ResearchStatus
from app.schemas import LoginRequest, ResearchCreate, ResearchDetail, ResearchSummary
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


@app.post("/auth/login", status_code=status.HTTP_204_NO_CONTENT)
def login(payload: LoginRequest, response: Response) -> None:
    if not authenticate(payload.username, payload.password, settings):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    set_session(response, settings)


@app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    clear_session(response)


@app.get("/auth/me")
def current_user(username: str = Depends(require_admin)) -> dict[str, str]:
    return {"username": username}


@app.get("/integrations")
def integrations(_: str = Depends(require_admin)) -> dict[str, dict[str, bool]]:
    """Configuration readiness only; no provider requests or credentials are returned."""
    return {
        "ifind": {"configured": bool(settings.secret_value(settings.ifind_mcp_api_key))},
        "deepseek": {"configured": bool(settings.secret_value(settings.deepseek_api_key))},
    }


@app.post("/researches", response_model=ResearchSummary, status_code=status.HTTP_202_ACCEPTED)
def create_research(
    payload: ResearchCreate,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> ResearchRun:
    if payload.as_of and payload.as_of > datetime.now(ZoneInfo("Asia/Shanghai")).date():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="截至日期不能晚于今天")
    run = ResearchRun(symbol=payload.symbol, as_of_date=payload.as_of, status=ResearchStatus.QUEUED)
    db.add(run)
    db.commit()
    db.refresh(run)
    try:
        if local_executor is not None:
            from app.services.research import run_research

            local_executor.submit(run_research, run.id)
        else:
            run_research_task.delay(run.id)
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
    _: str = Depends(require_admin),
) -> list[ResearchRun]:
    stmt = select(ResearchRun).order_by(ResearchRun.created_at.desc()).limit(limit)
    if symbol:
        stmt = stmt.where(ResearchRun.symbol.ilike(f"%{symbol.strip()}%"))
    if as_of:
        stmt = stmt.where(ResearchRun.as_of_date == as_of)
    return list(db.scalars(stmt))


def _get_research_or_404(research_id: str, db: Session) -> ResearchRun:
    stmt = select(ResearchRun).options(selectinload(ResearchRun.evidence)).where(ResearchRun.id == research_id)
    run = db.scalar(stmt)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该研究报告")
    return run


@app.get("/researches/{research_id}", response_model=ResearchDetail)
def get_research(research_id: str, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> ResearchRun:
    return _get_research_or_404(research_id, db)


@app.get("/researches/{research_id}/markdown")
def download_markdown(research_id: str, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> PlainTextResponse:
    run = _get_research_or_404(research_id, db)
    if not run.report_markdown:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="报告尚未生成")
    filename = f"research-{run.symbol}-{research_id[:8]}.md"
    return PlainTextResponse(
        run.report_markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=\"research-{research_id[:8]}.md\"; filename*=UTF-8''{quote(filename, safe='')}"},
    )
