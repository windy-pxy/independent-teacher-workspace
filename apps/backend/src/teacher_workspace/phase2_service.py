from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teacher_workspace.config import Settings
from teacher_workspace.models import (
    AIJob,
    DocumentVersion,
    DocumentVersionSource,
    Lesson,
    LessonDocument,
    PromptTemplate,
    PromptTemplateVersion,
    Student,
    StudentSubject,
    Subject,
    TeachingPlan,
    TeachingPlanItem,
)
from teacher_workspace.phase2_schemas import LessonPlanContent
from teacher_workspace.prompts import (
    DEFAULT_LESSON_PLAN_SYSTEM_PROMPT,
    DEFAULT_LESSON_PLAN_USER_PROMPT,
    LESSON_PLAN_TEMPLATE_KEY,
    lesson_plan_json_schema,
)
from teacher_workspace.providers.ai import AIRequest, create_ai_provider


async def ensure_default_lesson_plan_template(
    session: AsyncSession, owner_user_id: uuid.UUID
) -> tuple[PromptTemplate, PromptTemplateVersion]:
    template = await session.scalar(
        select(PromptTemplate).where(
            PromptTemplate.owner_user_id == owner_user_id,
            PromptTemplate.template_key == LESSON_PLAN_TEMPLATE_KEY,
            PromptTemplate.grade_band.is_(None),
            PromptTemplate.subject_id.is_(None),
            PromptTemplate.archived_at.is_(None),
        )
    )
    if template is None:
        template = PromptTemplate(
            owner_user_id=owner_user_id,
            template_key=LESSON_PLAN_TEMPLATE_KEY,
            name="通用结构化教案",
            purpose="LESSON_PLAN",
            grade_band=None,
            subject_id=None,
            current_version_number=1,
        )
        session.add(template)
        await session.flush()
        version = PromptTemplateVersion(
            template_id=template.id,
            version_number=1,
            system_prompt=DEFAULT_LESSON_PLAN_SYSTEM_PROMPT,
            user_prompt_template=DEFAULT_LESSON_PLAN_USER_PROMPT,
            output_schema=lesson_plan_json_schema(),
            change_reason="初始化通用结构化教案模板",
            created_by_user_id=owner_user_id,
        )
        session.add(version)
        await session.flush()
        return template, version
    current_version = await session.scalar(
        select(PromptTemplateVersion).where(
            PromptTemplateVersion.template_id == template.id,
            PromptTemplateVersion.version_number == template.current_version_number,
        )
    )
    if current_version is None:
        raise RuntimeError("Prompt template current version is missing")
    return template, current_version


async def resolve_template_version(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    template_id: uuid.UUID | None,
) -> PromptTemplateVersion:
    if template_id is None:
        _, version = await ensure_default_lesson_plan_template(session, owner_user_id)
        return version
    row = (
        await session.execute(
            select(PromptTemplate, PromptTemplateVersion)
            .join(
                PromptTemplateVersion,
                (PromptTemplateVersion.template_id == PromptTemplate.id)
                & (
                    PromptTemplateVersion.version_number
                    == PromptTemplate.current_version_number
                ),
            )
            .where(
                PromptTemplate.id == template_id,
                PromptTemplate.owner_user_id == owner_user_id,
                PromptTemplate.archived_at.is_(None),
            )
        )
    ).first()
    if row is None:
        raise LookupError("Prompt template not found")
    return row[1]


async def _lesson_context(
    session: AsyncSession, lesson_id: uuid.UUID, owner_user_id: uuid.UUID
) -> tuple[Lesson, dict[str, Any]]:
    row = (
        await session.execute(
            select(Lesson, StudentSubject, Student, Subject)
            .join(StudentSubject, StudentSubject.id == Lesson.student_subject_id)
            .join(Student, Student.id == StudentSubject.student_id)
            .join(Subject, Subject.id == StudentSubject.subject_id)
            .where(Lesson.id == lesson_id, Student.owner_user_id == owner_user_id)
        )
    ).first()
    if row is None:
        raise LookupError("Lesson not found")
    lesson, link, student, subject = row
    plan_rows = (
        await session.execute(
            select(TeachingPlan.name, TeachingPlanItem.title, TeachingPlanItem.status)
            .join(TeachingPlanItem, TeachingPlanItem.plan_id == TeachingPlan.id)
            .where(
                TeachingPlan.student_subject_id == link.id,
                TeachingPlan.archived_at.is_(None),
                TeachingPlanItem.archived_at.is_(None),
            )
            .order_by(TeachingPlan.name, TeachingPlanItem.sort_order)
        )
    ).all()
    plan_context = [
        {"plan": plan_name, "item": item_title, "status": status.value}
        for plan_name, item_title, status in plan_rows
    ]
    context: dict[str, Any] = {
        "student_alias": student.display_name,
        "grade": student.grade or "未填写",
        "subject": subject.name,
        "textbook_version": link.textbook_version or "未填写",
        "current_foundation": link.current_foundation or "未填写",
        "overall_goal": link.overall_goal or "未填写",
        "stage_goal": link.stage_goal or "未填写",
        "learning_characteristics": student.learning_characteristics or "未填写",
        "attention_notes": link.attention_notes or "未填写",
        "lesson_theme": lesson.theme,
        "lesson_type": lesson.lesson_type.value,
        "planned_minutes": lesson.planned_minutes,
        "special_requirements": lesson.special_requirements or "无",
        "plan_context": json.dumps(plan_context, ensure_ascii=False),
    }
    return lesson, context


async def execute_lesson_plan_job(
    job: AIJob,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> dict[str, object]:
    if job.owner_user_id is None or job.prompt_template_version_id is None:
        raise RuntimeError("Lesson plan job is missing ownership or template version")
    async with session_factory() as session:
        existing = await session.scalar(
            select(DocumentVersion).where(DocumentVersion.ai_job_id == job.id)
        )
        if existing is not None:
            return {
                "document_id": str(existing.document_id),
                "version_number": existing.version_number,
            }
        document_id = uuid.UUID(str(job.input_payload["document_id"]))
        document = await session.scalar(
            select(LessonDocument)
            .where(LessonDocument.id == document_id)
            .with_for_update()
        )
        template_version = await session.get(
            PromptTemplateVersion, job.prompt_template_version_id
        )
        if document is None or template_version is None:
            raise RuntimeError("Lesson plan job references missing records")
        lesson, context = await _lesson_context(
            session, document.lesson_id, job.owner_user_id
        )
        extra_requirements = str(job.input_payload.get("extra_requirements") or "无")
        context["extra_requirements"] = extra_requirements
        prompt = template_version.user_prompt_template.format_map(context)
        section = job.input_payload.get("section")
        if section:
            current_version = await session.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == document.id,
                    DocumentVersion.version_number == document.current_version_number,
                )
            )
            if current_version is None:
                raise RuntimeError("Cannot regenerate a section without an existing version")
            prompt += (
                "\n\n仅重新生成指定区块，但仍返回完整结构。"
                f"\n指定区块：{section}"
                f"\n教师要求：{job.input_payload.get('instructions')}"
                "\n当前教案 JSON："
                + json.dumps(current_version.content, ensure_ascii=False)
            )
        provider = create_ai_provider(settings)
        result = await provider.generate(
            AIRequest(
                prompt=prompt,
                instructions=template_version.system_prompt,
                schema=template_version.output_schema,
                context={"planned_minutes": lesson.planned_minutes},
            )
        )
        if result.structured is None:
            raise RuntimeError("AI provider did not return structured output")
        generated = LessonPlanContent.model_validate(result.structured)
        if sum(block.minutes for block in generated.schedule) != lesson.planned_minutes:
            raise RuntimeError("Generated schedule does not match the lesson duration")
        content = generated.model_dump(mode="json")
        source = DocumentVersionSource.AI_GENERATED
        if section:
            current_version = await session.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == document.id,
                    DocumentVersion.version_number == document.current_version_number,
                )
            )
            if current_version is None:
                raise RuntimeError("Current document version disappeared")
            merged = dict(current_version.content)
            merged[str(section)] = content[str(section)]
            content = LessonPlanContent.model_validate(merged).model_dump(mode="json")
            source = DocumentVersionSource.PARTIAL_REGENERATION
        next_number = int(
            await session.scalar(
                select(func.coalesce(func.max(DocumentVersion.version_number), 0)).where(
                    DocumentVersion.document_id == document.id
                )
            )
            or 0
        ) + 1
        version = DocumentVersion(
            document_id=document.id,
            version_number=next_number,
            source=source,
            content=content,
            change_summary=(
                f"AI 局部重新生成：{section}" if section else "AI 生成结构化教案草稿"
            ),
            ai_job_id=job.id,
            created_by_user_id=job.owner_user_id,
        )
        session.add(version)
        document.current_version_number = next_number
        document.version += 1
        await session.commit()
        return {
            "document_id": str(document.id),
            "version_number": next_number,
            "provider_request_id": result.provider_request_id or "",
            "input_tokens": result.input_tokens or 0,
            "output_tokens": result.output_tokens or 0,
        }
