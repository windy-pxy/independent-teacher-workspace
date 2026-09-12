from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from teacher_workspace.auth import require_ai_access, reserve_ai_usage
from teacher_workspace.models import AIUsageMonth, Base, User


@pytest.mark.asyncio
async def test_ai_quota_is_default_deny_and_atomically_bounded() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session, session.begin():
        disabled = User(username="quota-disabled", password_hash="fictional")
        enabled = User(
            username="quota-enabled",
            password_hash="fictional",
            ai_access_enabled=True,
            ai_monthly_job_limit=2,
        )
        session.add_all([disabled, enabled])

    async with factory() as session:
        with pytest.raises(HTTPException) as denied:
            await require_ai_access(disabled, session)
        assert denied.value.status_code == 403
        await require_ai_access(enabled, session)
        assert await session.scalar(
            select(AIUsageMonth).where(AIUsageMonth.owner_user_id == enabled.id)
        ) is None
        await reserve_ai_usage(enabled, session)
        await session.commit()
        await reserve_ai_usage(enabled, session)
        await session.commit()
        with pytest.raises(HTTPException) as exhausted:
            await reserve_ai_usage(enabled, session)
        assert exhausted.value.status_code == 429
        assert exhausted.value.detail["code"] == "AI_MONTHLY_QUOTA_REACHED"
        usage = await session.scalar(
            select(AIUsageMonth).where(
                AIUsageMonth.owner_user_id == enabled.id,
                AIUsageMonth.month_key == datetime.now(UTC).strftime("%Y-%m"),
            )
        )
        assert usage is not None
        assert usage.job_count == 2
    await engine.dispose()
