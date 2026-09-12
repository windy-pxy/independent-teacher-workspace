from __future__ import annotations

import argparse
import asyncio
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from teacher_workspace.account_deletion import purge_due_accounts
from teacher_workspace.config import get_settings
from teacher_workspace.db import dispose_engine, get_session_factory
from teacher_workspace.models import (
    AIJob,
    AIJobStatus,
    AuditLog,
    RegistrationInvite,
    User,
    UserSession,
)


def hash_invite(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def create_invite(label: str, max_uses: int, days: int) -> None:
    if max_uses < 1 or max_uses > 100 or days < 1 or days > 90:
        raise SystemExit("邀请码使用次数须为 1–100，有效期须为 1–90 天")
    code = secrets.token_urlsafe(32)
    invite = RegistrationInvite(
        code_hash=hash_invite(code),
        label=label,
        max_uses=max_uses,
        expires_at=datetime.now(UTC) + timedelta(days=days),
    )
    factory = get_session_factory()
    async with factory() as session, session.begin():
        session.add(invite)
        await session.flush()
        session.add(
            AuditLog(
                actor_user_id=None,
                action="REGISTRATION_INVITE_CREATED",
                entity_type="RegistrationInvite",
                entity_id=str(invite.id),
                change_summary={"label": label, "max_uses": max_uses, "days": days},
            )
        )
    print("邀请码只显示这一次，请通过可信渠道交给受邀教师：")
    print(code)


async def list_invites() -> None:
    factory = get_session_factory()
    async with factory() as session:
        invites = list(
            await session.scalars(
                select(RegistrationInvite).order_by(RegistrationInvite.created_at.desc())
            )
        )
    if not invites:
        print("当前没有邀请码")
        return
    for item in invites:
        state = "已撤销" if item.revoked_at else "有效/待核对到期时间"
        print(
            f"{item.id} | {item.label} | {item.uses_count}/{item.max_uses} | "
            f"到期 {item.expires_at.isoformat()} | {state}"
        )


async def revoke_invite(invite_id: uuid.UUID) -> None:
    factory = get_session_factory()
    async with factory() as session, session.begin():
        invite = await session.get(RegistrationInvite, invite_id, with_for_update=True)
        if invite is None:
            raise SystemExit("邀请码记录不存在")
        invite.revoked_at = datetime.now(UTC)
        session.add(
            AuditLog(
                actor_user_id=None,
                action="REGISTRATION_INVITE_REVOKED",
                entity_type="RegistrationInvite",
                entity_id=str(invite.id),
                change_summary={"label": invite.label},
            )
        )
    print(f"已撤销邀请码：{invite_id}")


async def set_ai_quota(username: str, limit: int) -> None:
    if limit < 0:
        raise SystemExit("AI 月度次数不能为负数")
    factory = get_session_factory()
    async with factory() as session, session.begin():
        user = await session.scalar(select(User).where(User.username == username).with_for_update())
        if user is None:
            raise SystemExit("教师账户不存在")
        user.ai_access_enabled = limit > 0
        user.ai_monthly_job_limit = limit
        if limit == 0:
            await session.execute(
                update(AIJob)
                .where(AIJob.owner_user_id == user.id, AIJob.status == AIJobStatus.QUEUED)
                .values(
                    status=AIJobStatus.CANCELED,
                    error_code="AI_ACCESS_REVOKED",
                    error_message="AI access was revoked before this task started",
                )
            )
        session.add(
            AuditLog(
                actor_user_id=None,
                action="PLATFORM_AI_QUOTA_CHANGED",
                entity_type="User",
                entity_id=str(user.id),
                change_summary={"enabled": limit > 0, "monthly_job_limit": limit},
            )
        )
    print(f"已更新 {username}：每月 AI 生成 {limit} 次")


async def set_active(username: str, active: bool) -> None:
    factory = get_session_factory()
    async with factory() as session, session.begin():
        user = await session.scalar(select(User).where(User.username == username).with_for_update())
        if user is None:
            raise SystemExit("教师账户不存在")
        if active and user.deletion_scheduled_for is not None:
            raise SystemExit("账户已申请删除；需由教师先在撤销期内取消删除申请")
        user.is_active = active
        if not active:
            user.ai_access_enabled = False
            user.ai_monthly_job_limit = 0
            await session.execute(
                update(UserSession)
                .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            )
            await session.execute(
                update(AIJob)
                .where(AIJob.owner_user_id == user.id, AIJob.status == AIJobStatus.QUEUED)
                .values(
                    status=AIJobStatus.CANCELED,
                    error_code="ACCOUNT_DISABLED",
                    error_message="Account was disabled before this task started",
                )
            )
        session.add(
            AuditLog(
                actor_user_id=None,
                action="PLATFORM_ACCOUNT_ACTIVATED" if active else "PLATFORM_ACCOUNT_DISABLED",
                entity_type="User",
                entity_id=str(user.id),
                change_summary={"active": active},
            )
        )
    print(f"已{'启用' if active else '停用'}教师账户：{username}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="在服务器终端安全管理教师账户")
    subcommands = parser.add_subparsers(dest="command", required=True)
    quota = subcommands.add_parser("ai", help="设置月度 AI 生成次数；0 表示关闭")
    quota.add_argument("username")
    quota.add_argument("--limit", type=int, required=True)
    for command in ("activate", "deactivate"):
        action = subcommands.add_parser(command, help=f"{command} 教师账户")
        action.add_argument("username")
        action.add_argument("--confirm", required=True, help="再次输入完全相同的账户名")
    purge = subcommands.add_parser("purge-due", help="永久清除已过撤销期的账户")
    purge.add_argument("--confirm", required=True, help="必须输入 PURGE-DUE")
    invite_create = subcommands.add_parser("invite-create", help="创建限次、限时邀请码")
    invite_create.add_argument("--label", required=True)
    invite_create.add_argument("--uses", type=int, default=1)
    invite_create.add_argument("--days", type=int, default=7)
    subcommands.add_parser("invite-list", help="列出邀请码元数据，不显示邀请码原文")
    invite_revoke = subcommands.add_parser("invite-revoke", help="撤销邀请码")
    invite_revoke.add_argument("invite_id", type=uuid.UUID)
    invite_revoke.add_argument("--confirm", required=True)
    return parser


async def execute(args: argparse.Namespace) -> None:
    try:
        if args.command == "ai":
            await set_ai_quota(args.username, args.limit)
        elif args.command in {"activate", "deactivate"}:
            if args.confirm != args.username:
                raise SystemExit("确认账户名不一致，操作已取消")
            await set_active(args.username, args.command == "activate")
        elif args.command == "purge-due":
            if args.confirm != "PURGE-DUE":
                raise SystemExit("确认文本不一致，操作已取消")
            count = await purge_due_accounts(get_session_factory(), get_settings())
            print(f"已永久清除 {count} 个到期账户")
        elif args.command == "invite-create":
            await create_invite(args.label, args.uses, args.days)
        elif args.command == "invite-list":
            await list_invites()
        else:
            if args.confirm != str(args.invite_id):
                raise SystemExit("确认邀请码 ID 不一致，操作已取消")
            await revoke_invite(args.invite_id)
    finally:
        await dispose_engine()


def main() -> None:
    asyncio.run(execute(build_parser().parse_args()))


if __name__ == "__main__":
    main()
