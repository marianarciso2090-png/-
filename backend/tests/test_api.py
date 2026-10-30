import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.pool import StaticPool

import app.db as db_module
import app.main as main_module
from app.models import CredentialSession, ResearchRun
from app.core.security import COOKIE_NAME


@pytest.fixture
def database(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    monkeypatch.setattr(db_module, "engine", engine)
    db_module.SessionLocal.configure(bind=engine)
    db_module.create_schema()
    monkeypatch.setattr(main_module, "local_executor", None)
    monkeypatch.setattr(main_module.run_research_task, "delay", lambda *_: None)
    yield engine


def connect(client, suffix="a"):
    response = client.post("/session", json={"ifind_mcp_api_key": f"demo-ifind-{suffix}", "deepseek_api_key": f"demo-deepseek-{suffix}"})
    assert response.status_code == 204


def test_keys_are_required_even_when_environment_has_keys(database):
    client = TestClient(main_module.app)
    assert client.get("/session").status_code == 401
    assert client.get("/integrations").status_code == 401
    assert client.post("/researches", json={"symbol": "600519"}).status_code == 401
    assert client.post("/auth/login", json={"username": "admin", "password": "change-me"}).status_code == 404
    response = client.post("/session", json={"ifind_mcp_api_key": "bad key", "deepseek_api_key": "private-test-key"})
    assert response.status_code == 422
    assert "private-test-key" not in response.text
    assert "bad key" not in response.text


def test_session_encrypts_keys_and_disconnect_revokes_cookie(database):
    client = TestClient(main_module.app)
    connect(client)
    assert client.get("/session").json() == {"connected": True}
    response = client.get("/integrations")
    assert response.json() == {"ifind": {"configured": True}, "deepseek": {"configured": True}}
    cookie = client.cookies.get(COOKIE_NAME)
    with db_module.SessionLocal() as db:
        session = db.scalar(select(CredentialSession))
        assert "demo-ifind" not in session.encrypted_keys
        assert "demo-deepseek" not in session.encrypted_keys
        assert "demo-" not in cookie
    assert client.delete("/session").status_code == 204
    client.cookies.set(COOKIE_NAME, cookie)
    assert client.get("/session").status_code == 401
    with db_module.SessionLocal() as db:
        assert db.scalar(select(CredentialSession)) is None


def test_report_isolation_restore_and_chinese_download(database):
    a, b = TestClient(main_module.app), TestClient(main_module.app)
    connect(a, "a")
    connect(b, "b")
    response = a.post("/researches", json={"symbol": "贵州茅台"})
    assert response.status_code == 202
    run_id = response.json()["id"]
    with db_module.SessionLocal() as db:
        run = db.get(ResearchRun, run_id)
        run.report_markdown = "# 中文报告"
        db.add(ResearchRun(symbol="legacy", owner_id=None))
        db.commit()
    assert len(a.get("/researches").json()) == 1
    assert b.get("/researches").json() == []
    assert b.get(f"/researches/{run_id}").status_code == 404
    assert b.get(f"/researches/{run_id}/markdown").status_code == 404
    download = a.get(f"/researches/{run_id}/markdown")
    assert download.status_code == 200 and download.text == "# 中文报告"
    assert "filename*=UTF-8''research-%E8%B4%B5" in download.headers["content-disposition"]
    a.delete("/session")
    connect(a, "a")
    assert a.get("/researches").json()[0]["id"] == run_id


def test_local_dispatch_only_passes_session_reference(database, monkeypatch):
    submitted = []
    class FakeExecutor:
        def submit(self, task, *args):
            submitted.append(args)
    monkeypatch.setattr(main_module, "local_executor", FakeExecutor())
    client = TestClient(main_module.app)
    connect(client)
    response = client.post("/researches", json={"symbol": "600519"})
    assert response.status_code == 202
    assert submitted[0][0] == response.json()["id"]
    with db_module.SessionLocal() as db:
        assert submitted[0][1] == db.scalar(select(CredentialSession)).id
    assert "demo-" not in str(submitted)


def test_expired_session_requires_keys_again(database):
    client = TestClient(main_module.app)
    connect(client)
    with db_module.SessionLocal() as db:
        db.scalar(select(CredentialSession)).expires_at = int(time.time()) - 1
        db.commit()
    assert client.get("/session").status_code == 401
    assert client.get("/researches").status_code == 401


def test_queued_job_with_revoked_keys_does_not_use_host_credentials(database, monkeypatch):
    import app.services.research as research
    def forbidden(*args, **kwargs):
        raise AssertionError("must not call a provider without session credentials")
    monkeypatch.setattr(research, "IFindClient", forbidden)
    monkeypatch.setattr(research, "DeepSeekClient", forbidden)
    client = TestClient(main_module.app)
    connect(client)
    run_id = client.post("/researches", json={"symbol": "600519"}).json()["id"]
    with db_module.SessionLocal() as db:
        session_id = db.scalar(select(CredentialSession)).id
    client.delete("/session")
    research.run_research(run_id, session_id)
    with db_module.SessionLocal() as db:
        run = db.get(ResearchRun, run_id)
        assert run.status.value == "failed"
        assert "密钥会话已失效" in run.error_message


def test_existing_database_keeps_legacy_reports_and_adds_owner(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE research_runs (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO research_runs (id) VALUES ('old-report')"))
    monkeypatch.setattr(db_module, "engine", engine)
    db_module.create_schema()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT id, owner_id FROM research_runs")).one() == ("old-report", None)
