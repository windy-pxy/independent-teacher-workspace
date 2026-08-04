from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teacher_workspace.config import Settings
from teacher_workspace.feedback_contract import LessonFeedbackContent
from teacher_workspace.models import (
    AIJob,
    FeedbackVersionSource,
    KnowledgePoint,
    Lesson,
    LessonFeedback,
    LessonFeedbackVersion,
    PromptTemplate,
    PromptTemplateVersion,
    ReviewStatus,
    Student,
    StudentMastery,
    StudentSubject,
    Subject,
    TeachingPlan,
    TeachingPlanItem,
)
from teacher_workspace.prompts import (
    DEFAULT_LESSON_FEEDBACK_SYSTEM_PROMPT,
    DEFAULT_LESSON_FEEDBACK_USER_PROMPT,
    LESSON_FEEDBACK_TEMPLATE_KEY,
    lesson_feedback_json_schema,
)
from teacher_workspace.providers.ai import AIRequest, create_ai_provider


def normalize_knowledge_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


async def ensure_default_feedback_template(
    session: AsyncSession, owner_user_id: uuid.UUID
) -> tuple[PromptTemplate, PromptTemplateVersion]:
    template = await session.scalar(
        select(PromptTemplate).where(
            PromptTemplate.owner_user_id == owner_user_id,
            PromptTemplate.template_key == LESSON_FEEDBACK_TEMPLATE_KEY,
            PromptTemplate.grade_band.is_(None),
            PromptTemplate.subject_id.is_(None),
            PromptTemplate.archived_at.is_(None),
        )
    )
    if template is None:
        template = PromptTemplate(
            owner_user_id=owner_user_id,
            template_key=LESSON_FEEDBACK_TEMPLATE_KEY,
            name="通用课后反馈整理",
            purpose="LESSON_FEEDBACK",
            grade_band=None,
            subject_id=None,
            current_version_number=1,
        )
        session.add(template)
        await session.flush()
        version = PromptTemplateVersion(
            template_id=template.id,
            version_number=1,
            system_prompt=DEFAULT_LESSON_FEEDBACK_SYSTEM_PROMPT,
            user_prompt_template=DEFAULT_LESSON_FEEDBACK_USER_PROMPT,
            output_schema=lesson_feedback_json_schema(),
            change_reason="初始化通用课后反馈整理模板",
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
        raise RuntimeError("Feedback prompt template current version is missing")
    return template, current_version


async def _feedback_context(
    session: AsyncSession, lesson_id: uuid.UUID, owner_user_id: uuid.UUID
) -> tuple[Lesson, StudentSubject, Subject, dict[str, Any], list[uuid.UUID]]:
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
        raise RuntimeError("Feedback job lesson was not found")
    lesson, student_subject, student, subject = row
    plan_rows = (
        await session.execute(
            select(TeachingPlanItem.id, TeachingPlanItem.title, TeachingPlanItem.status)
            .join(TeachingPlan, TeachingPlan.id == TeachingPlanItem.plan_id)
            .where(
                TeachingPlan.student_subject_id == student_subject.id,
                TeachingPlan.archived_at.is_(None),
                TeachingPlanItem.archived_at.is_(None),
            )
            .order_by(TeachingPlanItem.sort_order)
        )
    ).all()
    mastery_rows = (
        await session.execute(
            select(KnowledgePoint.id, KnowledgePoint.name, StudentMastery.level)
            .join(
                StudentMastery,
                StudentMastery.knowledge_point_id == KnowledgePoint.id,
            )
            .where(StudentMastery.student_subject_id == student_subject.id)
            .order_by(KnowledgePoint.name)
        )
    ).all()
    plan_context = [
        {"plan_item_id": str(item_id), "title": title, "status": status.value}
        for item_id, title, status in plan_rows
    ]
    mastery_context = [
        {"knowledge_point_id": str(point_id), "name": name, "level": level.value}
        for point_id, name, level in mastery_rows
    ]
    context: dict[str, Any] = {
        "student_alias": f"学生-{str(student.id)[-6:]}",
        "grade": student.grade or "未填写",
        "subject": subject.name,
        "lesson_theme": lesson.theme,
        "lesson_type": lesson.lesson_type.value,
        "planned_minutes": lesson.planned_minutes,
        "actual_minutes": lesson.actual_minutes or lesson.planned_minutes,
        "plan_context": json.dumps(plan_context, ensure_ascii=False),
        "mastery_context": json.dumps(mastery_context, ensure_ascii=False),
    }
    return lesson, student_subject, subject, context, [row[0] for row in plan_rows]


async def execute_feedback_job(
    job: AIJob,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> dict[str, object]:
    if job.owner_user_id is None or job.prompt_template_version_id is None:
        raise RuntimeError("Feedback job is missing ownership or template version")
    async with session_factory() as session:
        existing = await session.scalar(
            select(LessonFeedbackVersion).where(LessonFeedbackVersion.ai_job_id == job.id)
        )
        if existing is not None:
            return {
                "feedback_id": str(existing.feedback_id),
                "version_number": existing.version_number,
            }
        feedback_id = uuid.UUID(str(job.input_payload["feedback_id"]))
        source_number = int(job.input_payload["source_version_number"])
        feedback = await session.scalar(
            select(LessonFeedback)
            .where(LessonFeedback.id == feedback_id)
            .with_for_update()
        )
        template = await session.get(
            PromptTemplateVersion, job.prompt_template_version_id
        )
        if feedback is None or template is None:
            raise RuntimeError("Feedback job references missing records")
        source = await session.scalar(
            select(LessonFeedbackVersion).where(
                LessonFeedbackVersion.feedback_id == feedback.id,
                LessonFeedbackVersion.version_number == source_number,
            )
        )
        if source is None:
            raise RuntimeError("Feedback source version was not found")
        lesson, student_subject, subject, context, plan_item_ids = await _feedback_context(
            session, feedback.lesson_id, job.owner_user_id
        )
        context["raw_feedback"] = json.dumps(source.raw_input, ensure_ascii=False)
        context["organize_instructions"] = str(
            job.input_payload.get("instructions") or "无"
        )
        prompt = template.user_prompt_template.format_map(context)
        result = await create_ai_provider(settings).generate(
            AIRequest(
                prompt=prompt,
                instructions=template.system_prompt,
                schema=template.output_schema,
                context={
                    "task_type": "lesson_feedback",
                    "plan_item_ids": [str(item_id) for item_id in plan_item_ids],
                    "actual_minutes": lesson.actual_minutes or lesson.planned_minutes,
                },
            )
        )
        if result.structured is None:
            raise RuntimeError("AI provider did not return structured feedback")
        content = LessonFeedbackContent.model_validate(result.structured)
        allowed_plan_ids = set(plan_item_ids)
        if any(
            update.plan_item_id not in allowed_plan_ids
            for update in content.plan_progress_updates
        ):
            raise RuntimeError("AI feedback referenced an unavailable plan item")
        existing_point_ids = set(
            (
                await session.scalars(
                    select(KnowledgePoint.id).where(
                        KnowledgePoint.subject_id == subject.id,
                        KnowledgePoint.archived_at.is_(None),
                    )
                )
            ).all()
        )
        if any(
            update.knowledge_point_id is not None
            and update.knowledge_point_id not in existing_point_ids
            for update in content.mastery_updates
        ):
            raise RuntimeError("AI feedback referenced an unavailable knowledge point")
        next_number = int(
            await session.scalar(
                select(func.coalesce(func.max(LessonFeedbackVersion.version_number), 0)).where(
                    LessonFeedbackVersion.feedback_id == feedback.id
                )
            )
            or 0
        ) + 1
        version = LessonFeedbackVersion(
            feedback_id=feedback.id,
            version_number=next_number,
            source=FeedbackVersionSource.AI_ORGANIZED,
            status=ReviewStatus.DRAFT,
            raw_input=source.raw_input,
            content=content.model_dump(mode="json"),
            change_summary="AI 整理课后关键词",
            ai_job_id=job.id,
            created_by_user_id=job.owner_user_id,
        )
        source.status = ReviewStatus.SUPERSEDED
        session.add(version)
        feedback.current_version_number = next_number
        feedback.status = ReviewStatus.DRAFT
        feedback.version += 1
        await session.commit()
        return {
            "feedback_id": str(feedback.id),
            "version_number": next_number,
            "provider_request_id": result.provider_request_id or "",
            "input_tokens": result.input_tokens or 0,
            "output_tokens": result.output_tokens or 0,
        }
