import io
import zipfile
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from teacher_workspace.models import (
    Base,
    DocumentVersion,
    DocumentVersionSource,
    Lesson,
    LessonDocument,
    LessonStatus,
    LessonType,
    ReviewStatus,
    Student,
    StudentSubject,
    Subject,
    User,
)
from teacher_workspace.obsidian_export import build_obsidian_export, safe_segment


def test_safe_segment_rejects_windows_path_characters() -> None:
    assert safe_segment('../数学\\讲义:*?"') == "-数学-讲义----"
    assert safe_segment("章节#[一]") == "章节--一-"
    assert safe_segment("CON") == "未命名"


@pytest.mark.asyncio
async def test_obsidian_export_is_owned_readable_snapshot() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        owner = User(username="export-owner", password_hash="not-exported-secret")
        other = User(username="other-owner", password_hash="other-secret", is_active=False)
        session.add_all([owner, other])
        await session.flush()
        subject = Subject(owner_user_id=owner.id, name="虚构数学", normalized_name="虚构数学")
        student = Student(
            owner_user_id=owner.id,
            display_name="示例/学生",
            grade="八年级",
            learning_characteristics="喜欢结构化步骤",
        )
        other_student = Student(owner_user_id=other.id, display_name="不应导出的学生")
        session.add_all([subject, student, other_student])
        await session.flush()
        link = StudentSubject(
            student_id=student.id,
            subject_id=subject.id,
            textbook_version="虚构教材",
            stage_goal="掌握整式运算",
        )
        session.add(link)
        await session.flush()
        lesson = Lesson(
            student_subject_id=link.id,
            scheduled_start=datetime(2026, 8, 6, 2, 0, tzinfo=UTC),
            planned_minutes=90,
            actual_minutes=85,
            lesson_type=LessonType.NEW_LESSON,
            theme="整式/加减",
            status=LessonStatus.COMPLETED,
        )
        session.add(lesson)
        await session.flush()
        document = LessonDocument(
            lesson_id=lesson.id,
            title="虚构教案",
            status=ReviewStatus.APPROVED,
            current_version_number=1,
            approved_version_number=1,
            created_by_user_id=owner.id,
        )
        session.add(document)
        await session.flush()
        session.add(
            DocumentVersion(
                document_id=document.id,
                version_number=1,
                source=DocumentVersionSource.MANUAL_EDIT,
                status=ReviewStatus.APPROVED,
                content={"objectives": ["掌握合并同类项"]},
                change_summary="虚构批准版本",
                created_by_user_id=owner.id,
            )
        )
        await session.commit()

        exported = await build_obsidian_export(
            session, owner.id, now=datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
        )
    await engine.dispose()

    assert exported.student_count == 1
    assert exported.subject_count == 1
    assert exported.lesson_count == 1
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        names = archive.namelist()
        assert all(".." not in name and "\\" not in name for name in names)
        combined = "\n".join(
            archive.read(name).decode("utf-8") for name in names if name.endswith(".md")
        )
    assert "示例/学生" in combined
    assert "掌握合并同类项" in combined
    assert "不应导出的学生" not in combined
    assert "not-exported-secret" not in combined
