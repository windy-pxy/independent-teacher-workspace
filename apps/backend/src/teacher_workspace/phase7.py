from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_workspace.auth import CsrfUserDep, UserDep
from teacher_workspace.config import Settings, get_settings
from teacher_workspace.db import get_session
from teacher_workspace.models import (
    AuditLog,
    MaterialChunk,
    Student,
    StudentSubject,
    Subject,
    UploadedMaterial,
)
from teacher_workspace.phase7_schemas import (
    MaterialArchiveRequest,
    MaterialPurpose,
    MaterialResponse,
)
from teacher_workspace.phase7_service import (
    MaterialExtractionError,
    chunk_sections,
    detect_material_type,
    extract_sections,
)
from teacher_workspace.providers.storage import create_storage_provider
from teacher_workspace.storage_quota import ensure_upload_capacity

router = APIRouter(prefix="/api/v1", tags=["materials"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ALLOWED_PURPOSES = {
    "TEACHING_MATERIAL",
    "EXAM_PAPER",
    "OLD_LESSON_PLAN",
    "OTHER_REFERENCE",
}


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _owned_student_subject(
    session: AsyncSession, student_subject_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[StudentSubject, Student, Subject]:
    row = (
        await session.execute(
            select(StudentSubject, Student, Subject)
            .join(Student, Student.id == StudentSubject.student_id)
            .join(Subject, Subject.id == StudentSubject.subject_id)
            .where(
                StudentSubject.id == student_subject_id,
                Student.owner_user_id == user_id,
                Student.archived_at.is_(None),
                Subject.archived_at.is_(None),
            )
        )
    ).first()
    if row is None:
        raise api_error(404, "STUDENT_SUBJECT_NOT_FOUND", "学生学科档案不存在")
    return row[0], row[1], row[2]


async def _owned_material(
    session: AsyncSession, material_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False
) -> UploadedMaterial:
    statement = select(UploadedMaterial).where(
        UploadedMaterial.id == material_id,
        UploadedMaterial.owner_user_id == user_id,
        UploadedMaterial.archived_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    material = await session.scalar(statement)
    if material is None:
        raise api_error(404, "MATERIAL_NOT_FOUND", "资料不存在")
    return material


async def _material_response(session: AsyncSession, material: UploadedMaterial) -> MaterialResponse:
    if material.student_subject_id is None:
        raise api_error(409, "MATERIAL_CONTEXT_MISSING", "资料缺少学生学科关联")
    row = (
        await session.execute(
            select(
                Student.display_name,
                Subject.name,
                func.count(MaterialChunk.id),
                func.coalesce(func.sum(MaterialChunk.char_count), 0),
            )
            .join(StudentSubject, StudentSubject.student_id == Student.id)
            .join(Subject, Subject.id == StudentSubject.subject_id)
            .outerjoin(MaterialChunk, MaterialChunk.material_id == material.id)
            .where(StudentSubject.id == material.student_subject_id)
            .group_by(Student.display_name, Subject.name)
        )
    ).one()
    return MaterialResponse(
        id=material.id,
        student_subject_id=material.student_subject_id,
        student_name=row[0],
        subject_name=row[1],
        purpose=material.purpose,  # type: ignore[arg-type]
        display_name=material.display_name,
        mime_type=material.mime_type,
        size_bytes=material.size_bytes,
        processing_status=material.processing_status,
        chunk_count=int(row[2]),
        extracted_chars=int(row[3]),
        version=material.version,
        created_at=material.created_at,
    )


@router.get("/materials", response_model=list[MaterialResponse])
async def list_materials(
    user: UserDep,
    session: SessionDep,
    student_subject_id: uuid.UUID | None = None,
) -> list[MaterialResponse]:
    statement = select(UploadedMaterial).where(
        UploadedMaterial.owner_user_id == user.id,
        UploadedMaterial.purpose.in_(ALLOWED_PURPOSES),
        UploadedMaterial.archived_at.is_(None),
    )
    if student_subject_id is not None:
        statement = statement.where(UploadedMaterial.student_subject_id == student_subject_id)
    materials = (
        await session.scalars(statement.order_by(UploadedMaterial.created_at.desc()))
    ).all()
    return [await _material_response(session, item) for item in materials]


@router.post("/materials", response_model=MaterialResponse, status_code=status.HTTP_201_CREATED)
async def upload_material(
    request: Request,
    user: CsrfUserDep,
    session: SessionDep,
    settings: SettingsDep,
    student_subject_id: Annotated[uuid.UUID, Form()],
    purpose: Annotated[MaterialPurpose, Form()],
    file: Annotated[UploadFile, File()],
) -> MaterialResponse:
    student_subject, _, _ = await _owned_student_subject(session, student_subject_id, user.id)
    filename = PurePath(file.filename or "material").name[:255]
    content = await file.read(settings.max_upload_bytes + 1)
    if not content:
        raise api_error(422, "EMPTY_FILE", "资料文件不能为空")
    if len(content) > settings.max_upload_bytes:
        raise api_error(413, "FILE_TOO_LARGE", "资料超过允许的大小")
    try:
        mime_type, extension = detect_material_type(filename, file.content_type, content)
        sections = await asyncio.to_thread(extract_sections, mime_type, content)
        chunks = chunk_sections(sections)
    except MaterialExtractionError as exc:
        raise api_error(422, "MATERIAL_EXTRACTION_FAILED", str(exc)) from exc
    digest = hashlib.sha256(content).hexdigest()
    duplicate = await session.scalar(
        select(UploadedMaterial.id).where(
            UploadedMaterial.owner_user_id == user.id,
            UploadedMaterial.student_subject_id == student_subject.id,
            UploadedMaterial.sha256 == digest,
            UploadedMaterial.purpose.in_(ALLOWED_PURPOSES),
            UploadedMaterial.archived_at.is_(None),
        )
    )
    if duplicate is not None:
        raise api_error(409, "DUPLICATE_MATERIAL", "该学生学科已存在相同资料")
    await ensure_upload_capacity(session, user.id, len(content), settings)
    object_key = f"materials/{user.id}/{uuid.uuid4()}{extension}"
    storage = create_storage_provider(settings)
    await storage.save(object_key, content)
    try:
        material = UploadedMaterial(
            owner_user_id=user.id,
            student_subject_id=student_subject.id,
            purpose=purpose,
            display_name=filename,
            object_key=object_key,
            mime_type=mime_type,
            size_bytes=len(content),
            sha256=digest,
            processing_status="READY",
        )
        session.add(material)
        await session.flush()
        session.add_all(
            [
                MaterialChunk(
                    material_id=material.id,
                    chunk_index=index,
                    source_locator=chunk.locator,
                    content=chunk.text,
                    char_count=len(chunk.text),
                )
                for index, chunk in enumerate(chunks)
            ]
        )
        session.add(
            AuditLog(
                actor_user_id=user.id,
                action="MATERIAL_UPLOADED",
                entity_type="UploadedMaterial",
                entity_id=str(material.id),
                change_summary={
                    "purpose": purpose,
                    "mime_type": mime_type,
                    "size_bytes": len(content),
                    "chunk_count": len(chunks),
                },
                request_id=getattr(request.state, "request_id", None),
            )
        )
        await session.commit()
    except Exception:
        await session.rollback()
        await storage.delete(object_key)
        raise
    return await _material_response(session, material)


@router.get("/materials/{material_id}/download")
async def download_library_material(
    material_id: uuid.UUID, user: UserDep, session: SessionDep, settings: SettingsDep
) -> Response:
    material = await _owned_material(session, material_id, user.id)
    content = await create_storage_provider(settings).read(material.object_key)
    return Response(
        content=content,
        media_type=material.mime_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{quote(material.display_name)}"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/materials/{material_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
async def archive_material(
    material_id: uuid.UUID,
    payload: MaterialArchiveRequest,
    user: CsrfUserDep,
    session: SessionDep,
) -> Response:
    material = await _owned_material(session, material_id, user.id, lock=True)
    if material.version != payload.version:
        raise api_error(409, "VERSION_CONFLICT", "资料已更新，请刷新后重试")
    material.archived_at = datetime.now(UTC)
    material.version += 1
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="MATERIAL_ARCHIVED",
            entity_type="UploadedMaterial",
            entity_id=str(material.id),
            change_summary={"reason": payload.reason},
        )
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
