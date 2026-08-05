from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teacher_workspace.config import Settings
from teacher_workspace.models import (
    AIJob,
    GeneratedQuestionSet,
    GeneratedQuestionSetVersion,
    KnowledgePoint,
    PromptTemplate,
    PromptTemplateVersion,
    QuestionSetVersionSource,
    ReviewStatus,
    Student,
    StudentMastery,
    StudentSubject,
    Subject,
    UploadedMaterial,
    WrongQuestion,
    WrongQuestionVersion,
    WrongQuestionVersionSource,
)
from teacher_workspace.phase3_service import normalize_knowledge_name
from teacher_workspace.phase4_contract import (
    GeneratedQuestionSetContent,
    KnowledgePointRef,
    WrongQuestionContent,
)
from teacher_workspace.prompts import (
    DEFAULT_TARGETED_PRACTICE_SYSTEM_PROMPT,
    DEFAULT_TARGETED_PRACTICE_USER_PROMPT,
    DEFAULT_WRONG_QUESTION_RECOGNITION_SYSTEM_PROMPT,
    DEFAULT_WRONG_QUESTION_RECOGNITION_USER_PROMPT,
    TARGETED_PRACTICE_TEMPLATE_KEY,
    WRONG_QUESTION_RECOGNITION_TEMPLATE_KEY,
    targeted_practice_json_schema,
    wrong_question_recognition_json_schema,
)
from teacher_workspace.providers.ai import (
    AIImageInput,
    AIRequest,
    create_ai_provider,
    create_vision_ai_provider,
)
from teacher_workspace.providers.storage import create_storage_provider


async def ensure_phase4_template(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    template_key: str,
) -> PromptTemplateVersion:
    if template_key == WRONG_QUESTION_RECOGNITION_TEMPLATE_KEY:
        name = "通用错题图片识别"
        purpose = "WRONG_QUESTION_RECOGNITION"
        system_prompt = DEFAULT_WRONG_QUESTION_RECOGNITION_SYSTEM_PROMPT
        user_prompt = DEFAULT_WRONG_QUESTION_RECOGNITION_USER_PROMPT
        schema = wrong_question_recognition_json_schema()
    elif template_key == TARGETED_PRACTICE_TEMPLATE_KEY:
        name = "通用针对性练习"
        purpose = "TARGETED_PRACTICE"
        system_prompt = DEFAULT_TARGETED_PRACTICE_SYSTEM_PROMPT
        user_prompt = DEFAULT_TARGETED_PRACTICE_USER_PROMPT
        schema = targeted_practice_json_schema()
    else:
        raise RuntimeError("Unsupported Phase 4 template key")
    template = await session.scalar(
        select(PromptTemplate).where(
            PromptTemplate.owner_user_id == owner_user_id,
            PromptTemplate.template_key == template_key,
            PromptTemplate.grade_band.is_(None),
            PromptTemplate.subject_id.is_(None),
            PromptTemplate.archived_at.is_(None),
        )
    )
    if template is None:
        template = PromptTemplate(
            owner_user_id=owner_user_id,
            template_key=template_key,
            name=name,
            purpose=purpose,
            current_version_number=1,
        )
        session.add(template)
        await session.flush()
        created_version = PromptTemplateVersion(
            template_id=template.id,
            version_number=1,
            system_prompt=system_prompt,
            user_prompt_template=user_prompt,
            output_schema=schema,
            change_reason="初始化 Phase 4 通用模板",
            created_by_user_id=owner_user_id,
        )
        session.add(created_version)
        await session.flush()
        return created_version
    current_version = await session.scalar(
        select(PromptTemplateVersion).where(
            PromptTemplateVersion.template_id == template.id,
            PromptTemplateVersion.version_number == template.current_version_number,
        )
    )
    if current_version is None:
        raise RuntimeError("Phase 4 prompt template current version is missing")
    return current_version


async def owned_subject_context(
    session: AsyncSession, student_subject_id: uuid.UUID, owner_user_id: uuid.UUID
) -> tuple[StudentSubject, Student, Subject]:
    row = (
        await session.execute(
            select(StudentSubject, Student, Subject)
            .join(Student, Student.id == StudentSubject.student_id)
            .join(Subject, Subject.id == StudentSubject.subject_id)
            .where(
                StudentSubject.id == student_subject_id,
                Student.owner_user_id == owner_user_id,
                Subject.owner_user_id == owner_user_id,
                StudentSubject.archived_at.is_(None),
                Student.archived_at.is_(None),
                Subject.archived_at.is_(None),
            )
        )
    ).first()
    if row is None:
        raise RuntimeError("Student subject was not found")
    return row[0], row[1], row[2]


async def validate_knowledge_refs(
    session: AsyncSession, subject_id: uuid.UUID, refs: list[KnowledgePointRef]
) -> None:
    ids = {ref.knowledge_point_id for ref in refs if ref.knowledge_point_id is not None}
    if not ids:
        return
    found = set(
        (
            await session.scalars(
                select(KnowledgePoint.id).where(
                    KnowledgePoint.subject_id == subject_id,
                    KnowledgePoint.id.in_(ids),
                    KnowledgePoint.archived_at.is_(None),
                )
            )
        ).all()
    )
    if found != ids:
        raise ValueError("Content references an unavailable knowledge point")


async def resolve_knowledge_points(
    session: AsyncSession, subject_id: uuid.UUID, refs: list[KnowledgePointRef]
) -> list[KnowledgePoint]:
    await validate_knowledge_refs(session, subject_id, refs)
    points: list[KnowledgePoint] = []
    for ref in refs:
        point = (
            await session.get(KnowledgePoint, ref.knowledge_point_id)
            if ref.knowledge_point_id
            else None
        )
        if point is None:
            normalized = normalize_knowledge_name(ref.name)
            point = await session.scalar(
                select(KnowledgePoint).where(
                    KnowledgePoint.subject_id == subject_id,
                    KnowledgePoint.normalized_name == normalized,
                )
            )
            if point is None:
                point = KnowledgePoint(
                    subject_id=subject_id,
                    name=ref.name.strip(),
                    normalized_name=normalized,
                )
                session.add(point)
                await session.flush()
        points.append(point)
    return points


async def execute_wrong_question_recognition_job(
    job: AIJob,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> dict[str, object]:
    if job.owner_user_id is None or job.prompt_template_version_id is None:
        raise RuntimeError("Recognition job is missing ownership or template version")
    async with session_factory() as session:
        existing = await session.scalar(
            select(WrongQuestionVersion).where(WrongQuestionVersion.ai_job_id == job.id)
        )
        if existing is not None:
            return {
                "wrong_question_id": str(existing.wrong_question_id),
                "version_number": existing.version_number,
            }
        question_id = uuid.UUID(str(job.input_payload["wrong_question_id"]))
        source_number = int(job.input_payload["source_version_number"])
        question = await session.scalar(
            select(WrongQuestion).where(WrongQuestion.id == question_id).with_for_update()
        )
        template = await session.get(
            PromptTemplateVersion, job.prompt_template_version_id
        )
        source = await session.scalar(
            select(WrongQuestionVersion).where(
                WrongQuestionVersion.wrong_question_id == question_id,
                WrongQuestionVersion.version_number == source_number,
            )
        )
        if question is None or template is None or source is None:
            raise RuntimeError("Recognition job references missing records")
        if source.image_material_id is None:
            raise RuntimeError("Recognition source has no image")
        material = await session.get(UploadedMaterial, source.image_material_id)
        if material is None or material.owner_user_id != job.owner_user_id:
            raise RuntimeError("Recognition image was not found")
        student_subject, student, subject = await owned_subject_context(
            session, question.student_subject_id, job.owner_user_id
        )
        point_names = (
            await session.scalars(
                select(KnowledgePoint.name).where(
                    KnowledgePoint.subject_id == subject.id,
                    KnowledgePoint.archived_at.is_(None),
                )
            )
        ).all()
        source_content = WrongQuestionContent.model_validate(source.content)
        context = {
            "student_alias": f"学生-{str(student.id)[-6:]}",
            "grade": student.grade or "未填写",
            "subject": subject.name,
            "source_hint": source_content.source,
            "knowledge_point_context": json.dumps(point_names, ensure_ascii=False),
        }
        image_bytes = await create_storage_provider(settings).read(material.object_key)
        result = await create_vision_ai_provider(settings).generate(
            AIRequest(
                prompt=template.user_prompt_template.format_map(context),
                instructions=template.system_prompt,
                schema=template.output_schema,
                images=(AIImageInput(mime_type=material.mime_type, content=image_bytes),),
                context={
                    "task_type": "wrong_question_recognition",
                    "source_hint": source_content.source,
                },
            )
        )
        if result.structured is None:
            raise RuntimeError("Vision provider did not return structured content")
        content = WrongQuestionContent.model_validate(result.structured)
        await validate_knowledge_refs(session, subject.id, content.knowledge_points)
        next_number = int(
            await session.scalar(
                select(func.coalesce(func.max(WrongQuestionVersion.version_number), 0)).where(
                    WrongQuestionVersion.wrong_question_id == question.id
                )
            )
            or 0
        ) + 1
        version = WrongQuestionVersion(
            wrong_question_id=question.id,
            version_number=next_number,
            source=WrongQuestionVersionSource.AI_RECOGNIZED,
            status=ReviewStatus.DRAFT,
            content=content.model_dump(mode="json"),
            image_material_id=material.id,
            change_summary="AI 识别图片错题草稿",
            ai_job_id=job.id,
            created_by_user_id=job.owner_user_id,
        )
        source.status = ReviewStatus.SUPERSEDED
        session.add(version)
        question.current_version_number = next_number
        question.status = ReviewStatus.DRAFT
        question.version += 1
        material.processing_status = "RECOGNIZED_DRAFT"
        await session.commit()
        return {
            "wrong_question_id": str(question.id),
            "version_number": next_number,
            "provider_request_id": result.provider_request_id or "",
            "input_tokens": result.input_tokens or 0,
            "output_tokens": result.output_tokens or 0,
        }


async def execute_question_set_job(
    job: AIJob,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> dict[str, object]:
    if job.owner_user_id is None or job.prompt_template_version_id is None:
        raise RuntimeError("Question-set job is missing ownership or template version")
    async with session_factory() as session:
        existing = await session.scalar(
            select(GeneratedQuestionSetVersion).where(
                GeneratedQuestionSetVersion.ai_job_id == job.id
            )
        )
        if existing is not None:
            return {
                "question_set_id": str(existing.question_set_id),
                "version_number": existing.version_number,
            }
        set_id = uuid.UUID(str(job.input_payload["question_set_id"]))
        question_set = await session.scalar(
            select(GeneratedQuestionSet)
            .where(GeneratedQuestionSet.id == set_id)
            .with_for_update()
        )
        template = await session.get(
            PromptTemplateVersion, job.prompt_template_version_id
        )
        if question_set is None or template is None:
            raise RuntimeError("Question-set job references missing records")
        student_subject, student, subject = await owned_subject_context(
            session, question_set.student_subject_id, job.owner_user_id
        )
        parameters = question_set.parameters
        point_ids = [uuid.UUID(value) for value in parameters.get("knowledge_point_ids", [])]
        points = (
            (
                await session.scalars(
                    select(KnowledgePoint).where(
                        KnowledgePoint.id.in_(point_ids),
                        KnowledgePoint.subject_id == subject.id,
                        KnowledgePoint.archived_at.is_(None),
                    )
                )
            ).all()
            if point_ids
            else []
        )
        wrong_ids = [uuid.UUID(value) for value in parameters.get("wrong_question_ids", [])]
        wrong_rows: list[dict[str, object]] = []
        if wrong_ids:
            questions = (
                await session.scalars(
                    select(WrongQuestion).where(
                        WrongQuestion.id.in_(wrong_ids),
                        WrongQuestion.student_subject_id == student_subject.id,
                        WrongQuestion.approved_version_number.is_not(None),
                        WrongQuestion.archived_at.is_(None),
                    )
                )
            ).all()
            for question in questions:
                approved = await session.scalar(
                    select(WrongQuestionVersion).where(
                        WrongQuestionVersion.wrong_question_id == question.id,
                        WrongQuestionVersion.version_number
                        == question.approved_version_number,
                    )
                )
                if approved:
                    content = WrongQuestionContent.model_validate(approved.content)
                    wrong_rows.append(
                        {
                            "question_summary": content.question_text[:1000],
                            "error_reason": content.error_reason[:1000],
                            "mastery_status": question.mastery_status.value,
                        }
                    )
        mastery_rows = (
            await session.execute(
                select(KnowledgePoint.name, StudentMastery.level)
                .join(
                    StudentMastery,
                    StudentMastery.knowledge_point_id == KnowledgePoint.id,
                )
                .where(StudentMastery.student_subject_id == student_subject.id)
            )
        ).all()
        quantity = int(parameters["quantity"])
        point_names = [point.name for point in points]
        context: dict[str, Any] = {
            "student_alias": f"学生-{str(student.id)[-6:]}",
            "grade": student.grade or "未填写",
            "subject": subject.name,
            "student_level_context": json.dumps(
                {
                    "current_foundation": student_subject.current_foundation,
                    "stage_goal": student_subject.stage_goal,
                    "mastery": [
                        {"name": name, "level": level.value}
                        for name, level in mastery_rows
                    ],
                },
                ensure_ascii=False,
            ),
            "knowledge_point_context": json.dumps(point_names, ensure_ascii=False),
            "wrong_question_context": json.dumps(wrong_rows, ensure_ascii=False),
            "target_difficulty": str(parameters["target_difficulty"]),
            "quantity": quantity,
            "extra_requirements": str(parameters.get("extra_requirements") or "无"),
        }
        result = await create_ai_provider(settings).generate(
            AIRequest(
                prompt=template.user_prompt_template.format_map(context),
                instructions=template.system_prompt,
                schema=template.output_schema,
                context={
                    "task_type": "targeted_practice",
                    "quantity": quantity,
                    "target_difficulty": parameters["target_difficulty"],
                    "knowledge_point_name": point_names[0] if point_names else "综合薄弱点",
                    "title": question_set.title,
                },
            )
        )
        if result.structured is None:
            raise RuntimeError("AI provider did not return a structured question set")
        set_content = GeneratedQuestionSetContent.model_validate(result.structured)
        if len(set_content.questions) != quantity:
            raise RuntimeError("AI provider returned an unexpected question count")
        for item in set_content.questions:
            await validate_knowledge_refs(session, subject.id, item.knowledge_points)
        next_number = int(
            await session.scalar(
                select(
                    func.coalesce(func.max(GeneratedQuestionSetVersion.version_number), 0)
                ).where(GeneratedQuestionSetVersion.question_set_id == set_id)
            )
            or 0
        ) + 1
        version = GeneratedQuestionSetVersion(
            question_set_id=set_id,
            version_number=next_number,
            source=QuestionSetVersionSource.AI_GENERATED,
            status=ReviewStatus.DRAFT,
            content=set_content.model_dump(mode="json"),
            change_summary="AI 生成针对性练习草稿",
            ai_job_id=job.id,
            created_by_user_id=job.owner_user_id,
        )
        session.add(version)
        question_set.current_version_number = next_number
        question_set.status = ReviewStatus.DRAFT
        question_set.version += 1
        await session.commit()
        return {
            "question_set_id": str(set_id),
            "version_number": next_number,
            "provider_request_id": result.provider_request_id or "",
            "input_tokens": result.input_tokens or 0,
            "output_tokens": result.output_tokens or 0,
        }
