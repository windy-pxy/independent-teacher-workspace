from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pwdlib import PasswordHash
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_workspace.config import Settings, get_settings
from teacher_workspace.db import get_session
from teacher_workspace.models import AuditLog, User, UserSession
from teacher_workspace.phase1_schemas import AuthUser, LoginRequest, LoginResponse

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
password_hash = PasswordHash.recommended()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(UTC)


def unauthorized(message: str = "请先登录") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHENTICATED", "message": message},
    )


@dataclass(frozen=True)
class AuthContext:
    user: User
    user_session: UserSession


def validate_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.trusted_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "UNTRUSTED_ORIGIN", "message": "请求来源不受信任"},
        )


async def get_auth_context(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> AuthContext:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise unauthorized()
    statement = (
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(
            UserSession.token_hash == hash_token(raw_token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > utc_now(),
            User.is_active.is_(True),
        )
    )
    row = (await session.execute(statement)).first()
    if row is None:
        raise unauthorized("登录状态已失效，请重新登录")
    user_session, user = row
    return AuthContext(user=user, user_session=user_session)


AuthContextDep = Annotated[AuthContext, Depends(get_auth_context)]


async def require_user(context: AuthContextDep) -> User:
    return context.user


async def require_csrf(
    request: Request,
    context: AuthContextDep,
    settings: SettingsDep,
) -> User:
    validate_origin(request, settings)
    cookie_token = request.cookies.get(f"{settings.session_cookie_name}_csrf")
    header_token = request.headers.get("X-CSRF-Token")
    if (
        not cookie_token
        or not header_token
        or not secrets.compare_digest(cookie_token, header_token)
        or not secrets.compare_digest(
            hash_token(header_token), context.user_session.csrf_token_hash
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CSRF_FAILED", "message": "安全校验失败，请刷新页面后重试"},
        )
    return context.user


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> LoginResponse:
    validate_origin(request, settings)
    user = await session.scalar(
        select(User).where(User.username == payload.username.strip(), User.is_active.is_(True))
    )
    if user is None or not password_hash.verify(payload.password, user.password_hash):
        raise unauthorized("账户名或密码错误")

    raw_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = utc_now() + timedelta(hours=settings.session_ttl_hours)
    user_session = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hash_token(raw_token),
        csrf_token_hash=hash_token(csrf_token),
        expires_at=expires_at,
    )
    session.add(user_session)
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="USER_LOGGED_IN",
            entity_type="UserSession",
            entity_id=str(user_session.id),
            change_summary={"expires_at": expires_at.isoformat()},
            request_id=getattr(request.state, "request_id", None),
        )
    )
    await session.commit()
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        settings.session_cookie_name,
        raw_token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        f"{settings.session_cookie_name}_csrf",
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return LoginResponse(user=AuthUser(id=user.id, username=user.username))


UserDep = Annotated[User, Depends(require_user)]
CsrfUserDep = Annotated[User, Depends(require_csrf)]


@router.get("/me", response_model=AuthUser)
async def me(user: UserDep) -> AuthUser:
    return AuthUser(id=user.id, username=user.username)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    context: AuthContextDep,
    _: CsrfUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> None:
    await session.execute(
        update(UserSession)
        .where(UserSession.id == context.user_session.id)
        .values(revoked_at=utc_now())
    )
    await session.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(f"{settings.session_cookie_name}_csrf", path="/")
