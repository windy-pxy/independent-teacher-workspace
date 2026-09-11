"""Database-backed atomic fixed-window budgets, committed before credential work."""

import hashlib
import time

from fastapi import HTTPException
from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_workspace.models import AuthRateLimit


async def consume_auth_budget(session: AsyncSession, key: str, *, limit: int, seconds: int) -> None:
    now = int(time.time())
    window = now // seconds * seconds
    dialect = session.get_bind().dialect.name
    insert = sqlite_insert if dialect == "sqlite" else pg_insert
    stmt = insert(AuthRateLimit).values(
        key_hash=hashlib.sha256(key.encode()).hexdigest(), window_start=window, attempts=1
    )
    counted = stmt.on_conflict_do_update(
        index_elements=[AuthRateLimit.key_hash],
        set_={
            "window_start": window,
            "attempts": case(
                (AuthRateLimit.window_start == window, AuthRateLimit.attempts + 1), else_=1
            ),
        },
    ).returning(AuthRateLimit.attempts)
    count = await session.scalar(counted)
    await session.commit()
    if count is not None and count > limit:
        raise HTTPException(
            429,
            detail={"code": "AUTH_THROTTLED", "message": "尝试过多，请稍后再试"},
            headers={"Retry-After": str(window + seconds - now)},
        )
