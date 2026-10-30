from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import app.db as db_module
import app.main as main_module
from pydantic import SecretStr
from app.models import ResearchRun


def test_login_and_research_creation(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db_module.engine = engine
    db_module.SessionLocal.configure(bind=engine)
    monkeypatch.setattr(main_module.run_research_task, "delay", lambda _: None)

    with TestClient(main_module.app) as client:
        assert client.get("/auth/me").status_code == 401
        assert client.post("/auth/login", json={"username": "admin", "password": "change-me"}).status_code == 204
        created = client.post("/researches", json={"symbol": "600519", "as_of": date.today().isoformat()})
        assert created.status_code == 202
        body = created.json()
        assert body["symbol"] == "600519"
        assert body["status"] == "queued"
        detail = client.get(f"/researches/{body['id']}")
        assert detail.status_code == 200
        assert detail.json()["evidence"] == []
        with db_module.SessionLocal() as db:
            run = db.get(ResearchRun, body["id"])
            run.symbol = "贵州茅台"
            run.report_markdown = "# 中文报告"
            db.commit()
        download = client.get(f"/researches/{body['id']}/markdown")
        assert download.status_code == 200
        assert download.text == "# 中文报告"
        assert "filename*=UTF-8''research-%E8%B4%B5" in download.headers["content-disposition"]


def test_local_mode_dispatches_without_celery(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    db_module.engine = engine
    db_module.SessionLocal.configure(bind=engine)
    submitted: list[str] = []

    class FakeExecutor:
        def submit(self, _task, research_id: str) -> None:
            submitted.append(research_id)

    monkeypatch.setattr(main_module, "local_executor", FakeExecutor())
    monkeypatch.setattr(main_module.run_research_task, "delay", lambda _: (_ for _ in ()).throw(AssertionError("Celery called")))
    with TestClient(main_module.app) as client:
        assert client.post("/auth/login", json={"username": "admin", "password": "change-me"}).status_code == 204
        created = client.post("/researches", json={"symbol": "600519"})
        assert created.status_code == 202
        assert submitted == [created.json()["id"]]


def test_integrations_are_authenticated_and_do_not_expose_keys(monkeypatch) -> None:
    monkeypatch.setattr(main_module.settings, "ifind_mcp_api_key", SecretStr("private-ifind-key"))
    monkeypatch.setattr(main_module.settings, "deepseek_api_key", None)
    client = TestClient(main_module.app)
    assert client.get("/integrations").status_code == 401
    assert client.post("/auth/login", json={"username": "admin", "password": "change-me"}).status_code == 204
    response = client.get("/integrations")
    assert response.json() == {"ifind": {"configured": True}, "deepseek": {"configured": False}}
    assert "private-ifind-key" not in response.text
