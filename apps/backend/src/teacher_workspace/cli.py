import asyncio
import getpass

from pwdlib import PasswordHash
from sqlalchemy import func, select

from teacher_workspace.db import dispose_engine, get_session_factory
from teacher_workspace.models import AuditLog, User


async def _persist_admin(username: str, password: str) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        active_count = await session.scalar(
            select(func.count()).select_from(User).where(User.is_active)
        )
        if active_count:
            raise SystemExit("系统已存在启用的教师账户")
        user = User(username=username, password_hash=PasswordHash.recommended().hash(password))
        session.add(user)
        await session.flush()
        session.add(
            AuditLog(
                actor_user_id=user.id,
                action="USER_CREATED",
                entity_type="User",
                entity_id=str(user.id),
                change_summary={"username": username},
            )
        )
    print(f"已创建教师账户：{username}")


def create_admin() -> None:
    username = input("教师账户名: ").strip()
    if not username:
        raise SystemExit("账户名不能为空")
    password = getpass.getpass("密码（至少 12 个字符）: ")
    confirmation = getpass.getpass("再次输入密码: ")
    if password != confirmation:
        raise SystemExit("两次密码不一致")
    if len(password) < 12:
        raise SystemExit("密码至少需要 12 个字符")
    try:
        asyncio.run(_persist_admin(username, password))
    finally:
        asyncio.run(dispose_engine())


if __name__ == "__main__":
    create_admin()
