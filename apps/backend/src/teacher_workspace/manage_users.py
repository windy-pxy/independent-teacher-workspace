from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select, update

from teacher_workspace.account_deletion import purge_due_accounts
from teacher_workspace.config import get_settings
from teacher_workspace.db import dispose_engine, get_session_factory
from teacher_workspace.models import AIJob, AIJobStatus, AuditLog, User, UserSession


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


def main() -> None:
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
    args = parser.parse_args()
    try:
        if args.command == "ai":
            asyncio.run(set_ai_quota(args.username, args.limit))
        elif args.command in {"activate", "deactivate"}:
            if args.confirm != args.username:
                raise SystemExit("确认账户名不一致，操作已取消")
            asyncio.run(set_active(args.username, args.command == "activate"))
        else:
            if args.confirm != "PURGE-DUE":
                raise SystemExit("确认文本不一致，操作已取消")
            count = asyncio.run(purge_due_accounts(get_session_factory(), get_settings()))
            print(f"已永久清除 {count} 个到期账户")
    finally:
        asyncio.run(dispose_engine())


if __name__ == "__main__":
    main()
