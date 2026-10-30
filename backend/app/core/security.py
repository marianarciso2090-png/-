"""Browser-supplied keys, encrypted at rest; cookies contain random IDs only."""
import base64
import hashlib
import json
import secrets
import time

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db import get_db
from app.models import CredentialSession

COOKIE_NAME = "research_key_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60


def _cipher(settings: Settings) -> Fernet:
    material = settings.session_secret.get_secret_value().encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material).digest()))


def _session_id(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def create_session(response: Response, db: Session, settings: Settings, ifind_key: str, deepseek_key: str, previous_token: str | None) -> None:
    token = secrets.token_urlsafe(32)
    keys = json.dumps({"ifind_mcp_api_key": ifind_key, "deepseek_api_key": deepseek_key}, sort_keys=True)
    owner_id = hashlib.sha256(("research-workspace-v1:" + keys).encode()).hexdigest()
    db.execute(delete(CredentialSession).where(CredentialSession.expires_at <= int(time.time())))
    if previous_token:
        db.execute(delete(CredentialSession).where(CredentialSession.id == _session_id(previous_token)))
    db.add(CredentialSession(id=_session_id(token), owner_id=owner_id,
        encrypted_keys=_cipher(settings).encrypt(keys.encode()).decode(),
        expires_at=int(time.time()) + SESSION_MAX_AGE_SECONDS))
    db.commit()
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_MAX_AGE_SECONDS, httponly=True,
        secure=settings.is_production, samesite="strict", path="/")


def session_keys(session: CredentialSession, settings: Settings) -> dict[str, str]:
    if session.expires_at <= int(time.time()):
        raise ValueError("密钥会话已过期，请重新输入密钥")
    try:
        return json.loads(_cipher(settings).decrypt(session.encrypted_keys.encode(), ttl=SESSION_MAX_AGE_SECONDS))
    except (InvalidToken, ValueError):
        raise ValueError("密钥会话已失效，请重新输入密钥") from None


def require_session(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> CredentialSession:
    token = request.cookies.get(COOKIE_NAME)
    session = db.get(CredentialSession, _session_id(token)) if token else None
    if session is None:
        raise HTTPException(401, "请先输入 iFinD 和 DeepSeek 密钥")
    try:
        session_keys(session, settings)
    except ValueError as exc:
        db.delete(session)
        db.commit()
        raise HTTPException(401, str(exc)) from None
    return session
