from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pwdlib import PasswordHash
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from teacher_workspace.account_export import build_account_export
from teacher_workspace.account_schemas import (
    AccountDeletionRequest,
    AccountDeletionStatus,
    ConfirmPasswordRequest,
    PasswordChangeRequest,
    RecoveryResponse,
    RegisterRequest,
    RegisterResponse,
    RegistrationConfig,
    ResetPasswordRequest,
    SessionResponse,
    StorageUsageResponse,
)
from teacher_workspace.auth_limits import consume_auth_budget
from teacher_workspace.config import Settings, get_settings
from teacher_workspace.db import get_session
from teacher_workspace.login_throttle import LoginThrottle
from teacher_workspace.models import (
    AIJob,
    AIJobStatus,
    AIUsageMonth,
    AuditLog,
    RegistrationInvite,
    User,
    UserSession,
)
from teacher_workspace.phase1_schemas import AuthUser, LoginRequest, LoginResponse
from teacher_workspace.storage_quota import upload_usage_bytes

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
password_hash = PasswordHash.recommended()
dummy_password_hash = password_hash.hash(secrets.token_urlsafe(32))
login_throttle = LoginThrottle()

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
    expected_user_id = request.headers.get("X-Expected-User-ID")
    if expected_user_id and not secrets.compare_digest(expected_user_id, str(context.user.id)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ACCOUNT_CONTEXT_CHANGED",
                "message": "此标签页的登录账户已改变。为避免资料保存到错误账户，请刷新后继续",
            },
        )
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
    username = payload.username.strip()
    await consume_auth_budget(
        session, "auth:global", limit=settings.auth_global_limit_per_minute, seconds=60
    )
    await consume_auth_budget(
        session,
        f"login:{username.casefold()}",
        limit=settings.login_max_failures * 3,
        seconds=settings.login_window_seconds,
    )
    retry_after = await login_throttle.retry_after(username, settings.login_window_seconds)
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "LOGIN_THROTTLED", "message": "登录尝试过多，请稍后再试"},
            headers={"Retry-After": str(retry_after)},
        )
    user = await session.scalar(
        select(User).where(User.username == username, User.is_active.is_(True)).with_for_update()
    )
    password_matches = await run_in_threadpool(
        password_hash.verify,
        payload.password,
        user.password_hash if user is not None else dummy_password_hash,
    )
    if user is None or not password_matches:
        locked_for = await login_throttle.failure(
            username,
            max_failures=settings.login_max_failures,
            window_seconds=settings.login_window_seconds,
            lock_seconds=settings.login_lock_seconds,
        )
        if locked_for:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "LOGIN_THROTTLED", "message": "登录尝试过多，请稍后再试"},
                headers={"Retry-After": str(locked_for)},
            )
        raise unauthorized("账户名或密码错误")
    await login_throttle.success(username)

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
    return LoginResponse(
        user=AuthUser(
            id=user.id,
            username=user.username,
            deletion_scheduled_for=user.deletion_scheduled_for,
        )
    )


UserDep = Annotated[User, Depends(require_user)]
CsrfUserDep = Annotated[User, Depends(require_csrf)]


@router.get("/me", response_model=AuthUser)
async def me(user: UserDep) -> AuthUser:
    return AuthUser(
        id=user.id,
        username=user.username,
        deletion_scheduled_for=user.deletion_scheduled_for,
    )


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


@router.get("/registration", response_model=RegistrationConfig)
async def registration_config(settings: SettingsDep) -> RegistrationConfig:
    return RegistrationConfig(
        enabled=settings.registration_enabled,
        invite_required=settings.registration_invite_required,
        support_contact=settings.support_contact,
    )


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> RegisterResponse:
    validate_origin(request, settings)
    if not settings.registration_enabled:
        raise HTTPException(403, detail={"code": "REGISTRATION_CLOSED", "message": "暂未开放注册"})
    await consume_auth_budget(
        session, "register:global", limit=settings.registration_limit_per_hour, seconds=3600
    )
    invite: RegistrationInvite | None = None
    if settings.registration_invite_required:
        invite_hash = hash_token(payload.invite_code or "")
        invite = await session.scalar(
            select(RegistrationInvite)
            .where(
                RegistrationInvite.code_hash == invite_hash,
                RegistrationInvite.revoked_at.is_(None),
                RegistrationInvite.expires_at > utc_now(),
                RegistrationInvite.uses_count < RegistrationInvite.max_uses,
            )
            .with_for_update()
        )
        if invite is None:
            raise HTTPException(
                422,
                detail={
                    "code": "INVITATION_INVALID",
                    "message": "邀请码无效、已过期或已用完，请向邀请人确认",
                },
            )
    # Do password work for both new and unavailable usernames to reduce timing leakage.
    hashed = await run_in_threadpool(password_hash.hash, payload.password)
    duplicate = await session.scalar(
        select(User.id).where(func.lower(User.username) == payload.username)
    )
    if duplicate:
        raise HTTPException(
            409,
            detail={
                "code": "REGISTRATION_UNAVAILABLE",
                "message": "无法使用该账户名注册，请更换后重试",
            },
        )
    recovery_code = secrets.token_urlsafe(32)
    user = User(
        id=uuid.uuid4(),
        username=payload.username,
        password_hash=hashed,
        recovery_code_hash=hash_token(recovery_code),
        registration_invite_id=invite.id if invite else None,
        ai_access_enabled=False,
        ai_monthly_job_limit=0,
        privacy_notice_version=payload.privacy_notice_version,
        privacy_accepted_at=utc_now(),
    )
    session.add(user)
    try:
        if invite is not None:
            invite.uses_count += 1
        await session.flush()
        session.add(
            AuditLog(
                actor_user_id=user.id,
                action="USER_REGISTERED",
                entity_type="User",
                entity_id=str(user.id),
                change_summary={},
            )
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            409,
            detail={
                "code": "REGISTRATION_UNAVAILABLE",
                "message": "无法使用该账户名注册，请更换后重试",
            },
        ) from None
    return RegisterResponse(username=user.username, recovery_code=recovery_code)


@router.get("/storage-usage", response_model=StorageUsageResponse)
async def storage_usage(
    user: UserDep, session: SessionDep, settings: SettingsDep
) -> StorageUsageResponse:
    used = await upload_usage_bytes(session, user.id)
    return StorageUsageResponse(
        used_bytes=used,
        quota_bytes=settings.user_upload_quota_bytes,
        remaining_bytes=max(settings.user_upload_quota_bytes - used, 0),
    )


async def locked_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.scalar(
        select(User)
        .where(User.id == user_id, User.is_active.is_(True))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise unauthorized()
    return user


async def check_current_password(session: AsyncSession, user: User, value: str) -> None:
    await consume_auth_budget(session, f"password:{user.id}", limit=5, seconds=900)
    await locked_user(session, user.id)
    if not await run_in_threadpool(password_hash.verify, value, user.password_hash):
        raise unauthorized("当前密码错误")


async def revoke_sessions(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )


@router.post("/password", status_code=204)
async def change_password(
    payload: PasswordChangeRequest, user: CsrfUserDep, session: SessionDep
) -> None:
    await check_current_password(session, user, payload.current_password)
    if payload.new_password.isspace():
        raise HTTPException(
            422, detail={"code": "PASSWORD_INVALID", "message": "密码不能全部为空格"}
        )
    user.password_hash = await run_in_threadpool(password_hash.hash, payload.new_password)
    await revoke_sessions(session, user.id)
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="PASSWORD_CHANGED",
            entity_type="User",
            entity_id=str(user.id),
            change_summary={},
        )
    )
    await session.commit()


@router.post("/recovery-code", response_model=RecoveryResponse)
async def rotate_recovery_code(
    payload: ConfirmPasswordRequest, user: CsrfUserDep, session: SessionDep
) -> RecoveryResponse:
    await check_current_password(session, user, payload.current_password)
    code = secrets.token_urlsafe(32)
    user.recovery_code_hash = hash_token(code)
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="RECOVERY_CODE_ROTATED",
            entity_type="User",
            entity_id=str(user.id),
            change_summary={},
        )
    )
    await session.commit()
    return RecoveryResponse(recovery_code=code)


@router.post("/reset-password", status_code=204)
async def reset_password(
    payload: ResetPasswordRequest, request: Request, session: SessionDep, settings: SettingsDep
) -> None:
    validate_origin(request, settings)
    await consume_auth_budget(
        session, "auth:global", limit=settings.auth_global_limit_per_minute, seconds=60
    )
    await consume_auth_budget(
        session, f"recovery:{payload.username.strip().casefold()}", limit=5, seconds=900
    )
    user = await session.scalar(
        select(User)
        .where(User.username == payload.username.strip(), User.is_active.is_(True))
        .with_for_update()
    )
    expected = user.recovery_code_hash if user and user.recovery_code_hash else "0" * 64
    matches = secrets.compare_digest(hash_token(payload.recovery_code.strip()), expected)
    if not user or not matches:
        raise HTTPException(
            400, detail={"code": "RECOVERY_INVALID", "message": "账户名或恢复码无效"}
        )
    if payload.new_password.isspace():
        raise HTTPException(
            422, detail={"code": "PASSWORD_INVALID", "message": "密码不能全部为空格"}
        )
    user.password_hash = await run_in_threadpool(password_hash.hash, payload.new_password)
    user.recovery_code_hash = None
    await revoke_sessions(session, user.id)
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="PASSWORD_RECOVERED",
            entity_type="User",
            entity_id=str(user.id),
            change_summary={},
        )
    )
    await session.commit()


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(context: AuthContextDep, session: SessionDep) -> list[SessionResponse]:
    rows = await session.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == context.user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > utc_now(),
        )
        .order_by(UserSession.created_at.desc())
        .limit(100)
    )
    return [
        SessionResponse(
            id=row.id,
            created_at=row.created_at,
            expires_at=row.expires_at,
            is_current=row.id == context.user_session.id,
        )
        for row in rows
    ]


@router.post("/data-export.zip")
async def export_account_data(
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    exported = await build_account_export(session, user, settings)
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="ACCOUNT_DATA_EXPORTED",
            entity_type="User",
            entity_id=str(user.id),
            change_summary={
                "record_count": exported.record_count,
                "file_count": exported.file_count,
            },
            request_id=getattr(request.state, "request_id", None),
        )
    )
    await session.commit()
    return Response(
        content=exported.content,
        media_type="application/zip",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(exported.filename)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/deletion-request", response_model=AccountDeletionStatus)
async def request_account_deletion(
    payload: AccountDeletionRequest,
    request: Request,
    context: AuthContextDep,
    user: CsrfUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> AccountDeletionStatus:
    if user.deletion_scheduled_for is not None:
        return AccountDeletionStatus(scheduled_for=user.deletion_scheduled_for)
    if payload.confirm_username != user.username:
        raise HTTPException(
            422,
            detail={"code": "USERNAME_CONFIRMATION_FAILED", "message": "确认账户名不一致"},
        )
    await check_current_password(session, user, payload.current_password)
    now = utc_now()
    scheduled = now + timedelta(days=settings.account_deletion_grace_days)
    user.deletion_requested_at = now
    user.deletion_scheduled_for = scheduled
    await session.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.id != context.user_session.id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await session.execute(
        update(AIJob)
        .where(AIJob.owner_user_id == user.id, AIJob.status == AIJobStatus.QUEUED)
        .values(
            status=AIJobStatus.CANCELED,
            error_code="ACCOUNT_DELETION_REQUESTED",
            error_message="Account deletion canceled this queued task",
        )
    )
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="ACCOUNT_DELETION_REQUESTED",
            entity_type="User",
            entity_id=str(user.id),
            change_summary={"scheduled_for": scheduled.isoformat()},
            request_id=getattr(request.state, "request_id", None),
        )
    )
    await session.commit()
    return AccountDeletionStatus(scheduled_for=scheduled)


@router.post("/deletion-cancel", status_code=204)
async def cancel_account_deletion(
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
) -> None:
    if user.deletion_scheduled_for is None:
        return
    user.deletion_requested_at = None
    user.deletion_scheduled_for = None
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="ACCOUNT_DELETION_CANCELED",
            entity_type="User",
            entity_id=str(user.id),
            change_summary={},
            request_id=getattr(request.state, "request_id", None),
        )
    )
    await session.commit()


@router.post("/sessions/revoke-others", status_code=204)
async def revoke_other_sessions(
    context: AuthContextDep, _: CsrfUserDep, session: SessionDep
) -> None:
    await session.execute(
        update(UserSession)
        .where(
            UserSession.user_id == context.user.id,
            UserSession.id != context.user_session.id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=utc_now())
    )
    session.add(
        AuditLog(
            actor_user_id=context.user.id,
            action="OTHER_SESSIONS_REVOKED",
            entity_type="User",
            entity_id=str(context.user.id),
            change_summary={},
        )
    )
    await session.commit()


async def require_ai_access(user: CsrfUserDep, session: SessionDep) -> User:
    del session
    if (
        user.deletion_scheduled_for is not None
        or not user.ai_access_enabled
        or user.ai_monthly_job_limit <= 0
    ):
        raise HTTPException(
            403,
            detail={
                "code": "AI_ACCESS_DISABLED",
                "message": "此账户的 AI 生成权限尚未开通，可先使用学生、课程与手工记录功能",
            },
        )
    return user


async def reserve_ai_usage(user: User, session: AsyncSession) -> None:
    if (
        user.deletion_scheduled_for is not None
        or not user.ai_access_enabled
        or user.ai_monthly_job_limit <= 0
    ):
        raise HTTPException(
            403,
            detail={
                "code": "AI_ACCESS_DISABLED",
                "message": "此账户的 AI 生成权限尚未开通，可先使用学生、课程与手工记录功能",
            },
        )
    month_key = utc_now().strftime("%Y-%m")
    insert = sqlite_insert if session.get_bind().dialect.name == "sqlite" else pg_insert
    statement = insert(AIUsageMonth).values(
        owner_user_id=user.id,
        month_key=month_key,
        job_count=1,
        input_tokens=0,
        output_tokens=0,
        updated_at=utc_now(),
    )
    reserved = statement.on_conflict_do_update(
        index_elements=[AIUsageMonth.owner_user_id, AIUsageMonth.month_key],
        set_={
            "job_count": AIUsageMonth.job_count + 1,
            "updated_at": utc_now(),
        },
        where=AIUsageMonth.job_count < user.ai_monthly_job_limit,
    ).returning(AIUsageMonth.job_count)
    count = await session.scalar(reserved)
    if count is None:
        raise HTTPException(
            429,
            detail={
                "code": "AI_MONTHLY_QUOTA_REACHED",
                "message": "本月 AI 生成次数已用完，手工记录和编辑仍可继续使用",
            },
        )


AIUserDep = Annotated[User, Depends(require_ai_access)]
