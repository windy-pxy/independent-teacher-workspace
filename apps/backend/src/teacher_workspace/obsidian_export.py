from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_workspace.models import (
    DocumentVersion,
    KnowledgePoint,
    Lesson,
    LessonDocument,
    LessonFeedback,
    LessonFeedbackVersion,
    ReviewStatus,
    Student,
    StudentMastery,
    StudentSubject,
    Subject,
    TeachingPlan,
    TeachingPlanItem,
    WrongQuestion,
    WrongQuestionVersion,
)

INVALID_SEGMENT = re.compile(r'[<>:"/\\|?*#\[\]\x00-\x1f]')
WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
DISPLAY_TIMEZONE = timezone(timedelta(hours=8), "Asia/Shanghai")


@dataclass(frozen=True)
class ObsidianExport:
    content: bytes
    filename: str
    student_count: int
    subject_count: int
    lesson_count: int
    file_count: int


def safe_segment(value: str, fallback: str = "未命名") -> str:
    cleaned = INVALID_SEGMENT.sub("-", value).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned or cleaned.upper() in WINDOWS_RESERVED:
        cleaned = fallback
    return cleaned[:80].rstrip(" .") or fallback


def yaml_scalar(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return json.dumps(as_utc(value).isoformat())
    return json.dumps(str(value), ensure_ascii=False)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def frontmatter(values: dict[str, object]) -> str:
    lines = ["---"]
    lines.extend(f"{key}: {yaml_scalar(value)}" for key, value in values.items())
    lines.extend(["---", ""])
    return "\n".join(lines)


def text_or_dash(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    return text or "—"


def render_structured(value: object, level: int = 3) -> str:
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            title = str(key).replace("_", " ")
            if isinstance(item, (dict, list)):
                parts.append(
                    f"{'#' * min(level, 6)} {title}\n\n{render_structured(item, level + 1)}"
                )
            else:
                parts.append(f"- **{title}**：{text_or_dash(item)}")
        return "\n\n".join(parts)
    if isinstance(value, list):
        parts = []
        for index, item in enumerate(value, start=1):
            if isinstance(item, dict):
                parts.append(
                    f"{'#' * min(level, 6)} 条目 {index}\n\n{render_structured(item, level + 1)}"
                )
            else:
                parts.append(f"- {text_or_dash(item)}")
        return "\n\n".join(parts) if parts else "—"
    return text_or_dash(value)


def add_markdown(archive: zipfile.ZipFile, path: str, body: str) -> None:
    normalized = path.replace("\\", "/").strip("/")
    if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError("Unsafe Obsidian export path")
    archive.writestr(normalized, body.rstrip() + "\n")


async def approved_lesson_content(
    session: AsyncSession, lesson_id: uuid.UUID
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            select(DocumentVersion.content)
            .join(LessonDocument, LessonDocument.id == DocumentVersion.document_id)
            .where(
                LessonDocument.lesson_id == lesson_id,
                LessonDocument.approved_version_number == DocumentVersion.version_number,
                DocumentVersion.status == ReviewStatus.APPROVED,
            )
        )
    ).first()
    return row[0] if row else None


async def approved_feedback_content(
    session: AsyncSession, lesson_id: uuid.UUID
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            select(LessonFeedbackVersion.content)
            .join(LessonFeedback, LessonFeedback.id == LessonFeedbackVersion.feedback_id)
            .where(
                LessonFeedback.lesson_id == lesson_id,
                LessonFeedback.approved_version_number == LessonFeedbackVersion.version_number,
                LessonFeedbackVersion.status == ReviewStatus.APPROVED,
            )
        )
    ).first()
    return row[0] if row else None


async def build_obsidian_export(
    session: AsyncSession, owner_user_id: uuid.UUID, *, now: datetime | None = None
) -> ObsidianExport:
    generated_at = (now or datetime.now(UTC)).astimezone(UTC)
    students = (
        await session.scalars(
            select(Student)
            .where(Student.owner_user_id == owner_user_id, Student.archived_at.is_(None))
            .order_by(Student.display_name, Student.id)
        )
    ).all()
    output = io.BytesIO()
    subject_count = 0
    lesson_count = 0
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        add_markdown(
            archive,
            "README.md",
            frontmatter(
                {
                    "type": "teacher-workspace-export",
                    "generated_at": generated_at,
                    "read_only_snapshot": True,
                }
            )
            + "# 独立教师工作台 Obsidian 快照\n\n"
            + "这是 PostgreSQL 正式数据的单向只读快照。请勿把这里的修改当作已同步回工作台。\n\n"
            + "在 Obsidian 中选择“打开文件夹作为仓库”，打开解压后的目录即可。",
        )
        index_links: list[str] = []
        for student in students:
            student_folder = f"学生/{safe_segment(student.display_name)}--{str(student.id)[:8]}"
            index_links.append(f"- [[{student_folder}/档案|{student.display_name}]]")
            links = (
                await session.scalars(
                    select(StudentSubject)
                    .where(
                        StudentSubject.student_id == student.id,
                        StudentSubject.archived_at.is_(None),
                    )
                    .order_by(StudentSubject.created_at, StudentSubject.id)
                )
            ).all()
            subject_links: list[str] = []
            for link in links:
                subject = await session.get(Subject, link.subject_id)
                if (
                    subject is None
                    or subject.owner_user_id != owner_user_id
                    or subject.archived_at is not None
                ):
                    continue
                subject_count += 1
                subject_folder = (
                    f"{student_folder}/{safe_segment(subject.name)}--{str(link.id)[:8]}"
                )
                subject_links.append(f"- [[{subject_folder}/学科档案|{subject.name}]]")
                await add_subject_files(session, archive, subject_folder, student, subject, link)
                lessons = (
                    await session.scalars(
                        select(Lesson)
                        .where(
                            Lesson.student_subject_id == link.id,
                            Lesson.archived_at.is_(None),
                        )
                        .order_by(Lesson.scheduled_start, Lesson.id)
                    )
                ).all()
                lesson_count += len(lessons)
                for lesson in lessons:
                    await add_lesson_file(session, archive, subject_folder, lesson)
            profile = frontmatter(
                {
                    "type": "student",
                    "student_id": student.id,
                    "exported_at": generated_at,
                }
            )
            profile += f"# {student.display_name}\n\n"
            profile += f"- **年级**：{text_or_dash(student.grade)}\n"
            profile += f"- **地区**：{text_or_dash(student.region)}\n"
            profile += f"- **学校**：{text_or_dash(student.school)}\n"
            profile += f"- **学习特点**：{text_or_dash(student.learning_characteristics)}\n"
            profile += f"- **家长要求**：{text_or_dash(student.guardian_requirements)}\n"
            profile += f"- **备注**：{text_or_dash(student.notes)}\n\n"
            profile += "## 学科\n\n" + ("\n".join(subject_links) or "—")
            add_markdown(archive, f"{student_folder}/档案.md", profile)
        add_markdown(
            archive,
            "学生索引.md",
            frontmatter({"type": "student-index", "generated_at": generated_at})
            + "# 学生索引\n\n"
            + ("\n".join(index_links) or "当前没有学生记录。"),
        )
    content = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(content)) as completed_archive:
        file_count = len(completed_archive.namelist())
    return ObsidianExport(
        content=content,
        filename=f"teacher-workspace-obsidian-{generated_at:%Y%m%d-%H%M%S}.zip",
        student_count=len(students),
        subject_count=subject_count,
        lesson_count=lesson_count,
        file_count=file_count,
    )


async def add_subject_files(
    session: AsyncSession,
    archive: zipfile.ZipFile,
    folder: str,
    student: Student,
    subject: Subject,
    link: StudentSubject,
) -> None:
    body = frontmatter(
        {"type": "student-subject", "student_subject_id": link.id, "subject": subject.name}
    )
    body += f"# {student.display_name} · {subject.name}\n\n"
    body += f"- **教材版本**：{text_or_dash(link.textbook_version)}\n"
    body += f"- **当前基础**：{text_or_dash(link.current_foundation)}\n"
    body += f"- **总目标**：{text_or_dash(link.overall_goal)}\n"
    body += f"- **阶段目标**：{text_or_dash(link.stage_goal)}\n"
    body += f"- **教学要求**：{text_or_dash(link.teaching_requirements)}\n"
    body += f"- **注意事项**：{text_or_dash(link.attention_notes)}\n"
    add_markdown(archive, f"{folder}/学科档案.md", body)

    plans = (
        await session.scalars(
            select(TeachingPlan)
            .where(
                TeachingPlan.student_subject_id == link.id,
                TeachingPlan.archived_at.is_(None),
            )
            .order_by(TeachingPlan.created_at, TeachingPlan.id)
        )
    ).all()
    plan_parts = [frontmatter({"type": "teaching-plans", "student_subject_id": link.id})]
    plan_parts.append("# 教学计划")
    for plan in plans:
        plan_parts.append(f"## {plan.name}\n\n{text_or_dash(plan.description)}")
        items = (
            await session.scalars(
                select(TeachingPlanItem)
                .where(
                    TeachingPlanItem.plan_id == plan.id,
                    TeachingPlanItem.archived_at.is_(None),
                )
                .order_by(TeachingPlanItem.sort_order, TeachingPlanItem.id)
            )
        ).all()
        plan_parts.extend(
            f"- [{('x' if item.status.value == 'COMPLETED' else ' ')}] "
            f"{item.title} · {item.status.value} · "
            f"{item.actual_minutes}/{item.estimated_minutes} 分钟"
            for item in items
        )
    add_markdown(archive, f"{folder}/教学计划.md", "\n\n".join(plan_parts))

    mastery_rows = (
        await session.execute(
            select(KnowledgePoint.name, StudentMastery.level, StudentMastery.updated_at)
            .join(KnowledgePoint, KnowledgePoint.id == StudentMastery.knowledge_point_id)
            .where(StudentMastery.student_subject_id == link.id)
            .order_by(KnowledgePoint.name)
        )
    ).all()
    mastery = frontmatter({"type": "mastery", "student_subject_id": link.id})
    mastery += "# 知识点掌握\n\n"
    mastery += (
        "\n".join(
            f"- **{name}**：{level.value}（更新于 {as_utc(updated_at):%Y-%m-%d}）"
            for name, level, updated_at in mastery_rows
        )
        or "—"
    )
    add_markdown(archive, f"{folder}/知识点掌握.md", mastery)

    questions = (
        await session.execute(
            select(WrongQuestion, WrongQuestionVersion)
            .join(
                WrongQuestionVersion,
                (WrongQuestionVersion.wrong_question_id == WrongQuestion.id)
                & (WrongQuestionVersion.version_number == WrongQuestion.approved_version_number),
            )
            .where(
                WrongQuestion.student_subject_id == link.id,
                WrongQuestion.status == ReviewStatus.APPROVED,
                WrongQuestion.archived_at.is_(None),
            )
            .order_by(WrongQuestion.created_at, WrongQuestion.id)
        )
    ).all()
    wrong_parts = [frontmatter({"type": "wrong-questions", "student_subject_id": link.id})]
    wrong_parts.append("# 错题")
    for index, (question, version) in enumerate(questions, start=1):
        wrong_parts.append(
            f"## 错题 {index}\n\n- **掌握状态**：{question.mastery_status.value}\n"
            f"- **复习次数**：{question.review_count}\n\n{render_structured(version.content)}"
        )
    add_markdown(archive, f"{folder}/错题.md", "\n\n".join(wrong_parts))


async def add_lesson_file(
    session: AsyncSession, archive: zipfile.ZipFile, folder: str, lesson: Lesson
) -> None:
    local_time = as_utc(lesson.scheduled_start).astimezone(DISPLAY_TIMEZONE)
    path = (
        f"{folder}/课程/{local_time:%Y-%m-%d-%H%M}-"
        f"{safe_segment(lesson.theme)}--{str(lesson.id)[:8]}.md"
    )
    body = frontmatter(
        {
            "type": "lesson",
            "lesson_id": lesson.id,
            "scheduled_start": lesson.scheduled_start,
            "status": lesson.status.value,
            "lesson_type": lesson.lesson_type.value,
        }
    )
    body += f"# {lesson.theme}\n\n"
    body += f"- **计划时长**：{lesson.planned_minutes} 分钟\n"
    body += f"- **实际时长**：{text_or_dash(lesson.actual_minutes)} 分钟\n"
    body += f"- **特殊要求**：{text_or_dash(lesson.special_requirements)}\n"
    document = await approved_lesson_content(session, lesson.id)
    feedback = await approved_feedback_content(session, lesson.id)
    if document is not None:
        body += "\n## 已批准教案\n\n" + render_structured(document)
    if feedback is not None:
        body += "\n\n## 已批准课后反馈\n\n" + render_structured(feedback)
    add_markdown(archive, path, body)
