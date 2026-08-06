from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_workspace.auth import CsrfUserDep
from teacher_workspace.db import get_session
from teacher_workspace.models import AuditLog
from teacher_workspace.obsidian_export import build_obsidian_export

router = APIRouter(prefix="/api/v1", tags=["exports"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/exports/obsidian.zip")
async def export_obsidian_snapshot(
    request: Request, user: CsrfUserDep, session: SessionDep
) -> Response:
    exported = await build_obsidian_export(session, user.id)
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="OBSIDIAN_SNAPSHOT_EXPORTED",
            entity_type="User",
            entity_id=str(user.id),
            change_summary={
                "student_count": exported.student_count,
                "subject_count": exported.subject_count,
                "lesson_count": exported.lesson_count,
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
            "Content-Disposition": (f"attachment; filename*=UTF-8''{exported.filename}"),
            "X-Content-Type-Options": "nosniff",
        },
    )
