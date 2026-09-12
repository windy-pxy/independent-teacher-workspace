from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_workspace.config import Settings
from teacher_workspace.models import UploadedMaterial, User


async def upload_usage_bytes(session: AsyncSession, user_id: uuid.UUID) -> int:
    value = await session.scalar(
        select(func.coalesce(func.sum(UploadedMaterial.size_bytes), 0)).where(
            UploadedMaterial.owner_user_id == user_id
        )
    )
    return int(value or 0)


async def ensure_upload_capacity(
    session: AsyncSession,
    user_id: uuid.UUID,
    incoming_bytes: int,
    settings: Settings,
) -> int:
    locked = await session.scalar(select(User.id).where(User.id == user_id).with_for_update())
    if locked is None:
        raise HTTPException(
            401,
            detail={"code": "UNAUTHENTICATED", "message": "请先登录"},
        )
    used = await upload_usage_bytes(session, user_id)
    if used + incoming_bytes > settings.user_upload_quota_bytes:
        raise HTTPException(
            413,
            detail={
                "code": "USER_STORAGE_QUOTA_REACHED",
                "message": "账户上传空间已满，请联系管理员调整容量",
                "details": {
                    "used_bytes": used,
                    "quota_bytes": settings.user_upload_quota_bytes,
                },
            },
        )
    return used
