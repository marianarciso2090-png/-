import secrets

from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

from app.core.config import Settings, get_settings

COOKIE_NAME = "stock_research_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 12


def authenticate(username: str, password: str, settings: Settings) -> bool:
    configured_password = settings.admin_password.get_secret_value()
    return secrets.compare_digest(username, settings.admin_username) and secrets.compare_digest(
        password, configured_password
    )


def _signer(settings: Settings) -> TimestampSigner:
    return TimestampSigner(settings.session_secret.get_secret_value(), salt="stock-research-admin")


def set_session(response: Response, settings: Settings) -> None:
    token = _signer(settings).sign(settings.admin_username.encode("utf-8")).decode("utf-8")
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def require_admin(request: Request, settings: Settings = Depends(get_settings)) -> str:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    try:
        username = _signer(settings).unsign(token, max_age=SESSION_MAX_AGE_SECONDS).decode("utf-8")
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期") from None
    if not secrets.compare_digest(username, settings.admin_username):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效登录")
    return username
