from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_workspace.db import get_session
from teacher_workspace.schemas import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    return HealthResponse(service="api")


async def database_readiness(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    try:
        await session.execute(text("SELECT 1"))
        result = await session.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        migration = result.scalar_one_or_none()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "DATABASE_NOT_READY", "message": "Database is not ready"},
        ) from exc
    return {"database": "ok", "migration": migration or "unversioned"}


@router.get("/ready", response_model=HealthResponse)
async def ready(
    readiness: Annotated[dict[str, Any], Depends(database_readiness)],
) -> HealthResponse:
    return HealthResponse(service="api", **readiness)
