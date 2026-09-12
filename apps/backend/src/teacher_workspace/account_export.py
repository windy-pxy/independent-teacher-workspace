from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from io import BytesIO
from pathlib import PurePath
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from teacher_workspace import models
from teacher_workspace.config import Settings
from teacher_workspace.providers.storage import create_storage_provider


@dataclass(frozen=True)
class AccountExport:
    content: bytes
    filename: str
    record_count: int
    file_count: int


def json_value(value: object) -> object:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def row_data(row: models.Base) -> dict[str, object]:
    return {
        column.key: json_value(getattr(row, column.key))
        for column in inspect(type(row)).columns
    }


async def rows(
    session: AsyncSession,
    model: type[models.Base],
    condition: ColumnElement[bool],
) -> list[models.Base]:
    return list(await session.scalars(select(model).where(condition)))


def ids(items: list[models.Base]) -> set[uuid.UUID]:
    return {item.id for item in items if hasattr(item, "id")}  # type: ignore[attr-defined]


def safe_name(value: str) -> str:
    name = PurePath(value).name
    return "".join("_" if char in '<>:"/\\|?*' or ord(char) < 32 else char for char in name)[:180]


async def build_account_export(
    session: AsyncSession, user: models.User, settings: Settings
) -> AccountExport:
    exported: dict[str, list[models.Base]] = {}
    exported["subjects"] = await rows(
        session, models.Subject, models.Subject.owner_user_id == user.id
    )
    exported["students"] = await rows(
        session, models.Student, models.Student.owner_user_id == user.id
    )
    subject_ids = ids(exported["subjects"])
    student_ids = ids(exported["students"])
    exported["student_subjects"] = await rows(
        session, models.StudentSubject, models.StudentSubject.student_id.in_(student_ids)
    )
    link_ids = ids(exported["student_subjects"])
    exported["teaching_plans"] = await rows(
        session, models.TeachingPlan, models.TeachingPlan.student_subject_id.in_(link_ids)
    )
    plan_ids = ids(exported["teaching_plans"])
    exported["teaching_plan_items"] = await rows(
        session, models.TeachingPlanItem, models.TeachingPlanItem.plan_id.in_(plan_ids)
    )
    exported["teaching_plan_revisions"] = await rows(
        session, models.TeachingPlanRevision, models.TeachingPlanRevision.plan_id.in_(plan_ids)
    )
    exported["lessons"] = await rows(
        session, models.Lesson, models.Lesson.student_subject_id.in_(link_ids)
    )
    lesson_ids = ids(exported["lessons"])
    exported["lesson_plan_items"] = await rows(
        session, models.LessonPlanItem, models.LessonPlanItem.lesson_id.in_(lesson_ids)
    )
    exported["payments"] = await rows(
        session, models.Payment, models.Payment.owner_user_id == user.id
    )
    payment_ids = ids(exported["payments"])
    exported["payment_allocations"] = await rows(
        session, models.PaymentAllocation, models.PaymentAllocation.payment_id.in_(payment_ids)
    )
    exported["prompt_templates"] = await rows(
        session, models.PromptTemplate, models.PromptTemplate.owner_user_id == user.id
    )
    template_ids = ids(exported["prompt_templates"])
    exported["prompt_template_versions"] = await rows(
        session,
        models.PromptTemplateVersion,
        models.PromptTemplateVersion.template_id.in_(template_ids),
    )
    exported["lesson_documents"] = await rows(
        session, models.LessonDocument, models.LessonDocument.lesson_id.in_(lesson_ids)
    )
    document_ids = ids(exported["lesson_documents"])
    exported["document_versions"] = await rows(
        session, models.DocumentVersion, models.DocumentVersion.document_id.in_(document_ids)
    )
    exported["lesson_feedbacks"] = await rows(
        session, models.LessonFeedback, models.LessonFeedback.lesson_id.in_(lesson_ids)
    )
    feedback_ids = ids(exported["lesson_feedbacks"])
    exported["lesson_feedback_versions"] = await rows(
        session,
        models.LessonFeedbackVersion,
        models.LessonFeedbackVersion.feedback_id.in_(feedback_ids),
    )
    feedback_version_ids = ids(exported["lesson_feedback_versions"])
    exported["knowledge_points"] = await rows(
        session, models.KnowledgePoint, models.KnowledgePoint.subject_id.in_(subject_ids)
    )
    knowledge_ids = ids(exported["knowledge_points"])
    exported["student_masteries"] = await rows(
        session, models.StudentMastery, models.StudentMastery.student_subject_id.in_(link_ids)
    )
    mastery_ids = ids(exported["student_masteries"])
    exported["mastery_evidence"] = await rows(
        session,
        models.MasteryEvidence,
        models.MasteryEvidence.mastery_id.in_(mastery_ids)
        & models.MasteryEvidence.feedback_version_id.in_(feedback_version_ids),
    )
    exported["uploaded_materials"] = await rows(
        session, models.UploadedMaterial, models.UploadedMaterial.owner_user_id == user.id
    )
    material_ids = ids(exported["uploaded_materials"])
    exported["material_chunks"] = await rows(
        session, models.MaterialChunk, models.MaterialChunk.material_id.in_(material_ids)
    )
    exported["wrong_questions"] = await rows(
        session, models.WrongQuestion, models.WrongQuestion.student_subject_id.in_(link_ids)
    )
    wrong_ids = ids(exported["wrong_questions"])
    exported["wrong_question_versions"] = await rows(
        session,
        models.WrongQuestionVersion,
        models.WrongQuestionVersion.wrong_question_id.in_(wrong_ids),
    )
    exported["wrong_question_knowledge_points"] = await rows(
        session,
        models.WrongQuestionKnowledgePoint,
        models.WrongQuestionKnowledgePoint.wrong_question_id.in_(wrong_ids)
        & models.WrongQuestionKnowledgePoint.knowledge_point_id.in_(knowledge_ids),
    )
    exported["wrong_question_reviews"] = await rows(
        session,
        models.WrongQuestionReview,
        models.WrongQuestionReview.wrong_question_id.in_(wrong_ids),
    )
    exported["generated_question_sets"] = await rows(
        session,
        models.GeneratedQuestionSet,
        models.GeneratedQuestionSet.student_subject_id.in_(link_ids),
    )
    set_ids = ids(exported["generated_question_sets"])
    exported["generated_question_set_versions"] = await rows(
        session,
        models.GeneratedQuestionSetVersion,
        models.GeneratedQuestionSetVersion.question_set_id.in_(set_ids),
    )
    exported["generated_questions"] = await rows(
        session,
        models.GeneratedQuestion,
        models.GeneratedQuestion.question_set_id.in_(set_ids),
    )
    question_ids = ids(exported["generated_questions"])
    exported["generated_question_knowledge_points"] = await rows(
        session,
        models.GeneratedQuestionKnowledgePoint,
        models.GeneratedQuestionKnowledgePoint.generated_question_id.in_(question_ids)
        & models.GeneratedQuestionKnowledgePoint.knowledge_point_id.in_(knowledge_ids),
    )
    exported["ai_jobs"] = await rows(session, models.AIJob, models.AIJob.owner_user_id == user.id)
    job_ids = ids(exported["ai_jobs"])
    exported["ai_job_attempts"] = await rows(
        session, models.AIJobAttempt, models.AIJobAttempt.job_id.in_(job_ids)
    )
    exported["ai_usage_months"] = await rows(
        session, models.AIUsageMonth, models.AIUsageMonth.owner_user_id == user.id
    )
    exported["audit_logs"] = await rows(
        session, models.AuditLog, models.AuditLog.actor_user_id == user.id
    )

    buffer = BytesIO()
    storage = create_storage_provider(settings)
    missing_files: list[str] = []
    file_count = 0
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        account = {
            "id": str(user.id),
            "username": user.username,
            "created_at": user.created_at.isoformat(),
            "privacy_notice_version": user.privacy_notice_version,
            "privacy_accepted_at": (
                user.privacy_accepted_at.isoformat() if user.privacy_accepted_at else None
            ),
        }
        archive.writestr("account.json", json.dumps(account, ensure_ascii=False, indent=2))
        record_count = 0
        for name, items in exported.items():
            record_count += len(items)
            archive.writestr(
                f"records/{name}.json",
                json.dumps([row_data(item) for item in items], ensure_ascii=False, indent=2),
            )
        for material in exported["uploaded_materials"]:
            assert isinstance(material, models.UploadedMaterial)
            try:
                content = await storage.read(material.object_key)
            except Exception:
                missing_files.append(f"material:{material.id}")
            else:
                archive.writestr(
                    f"attachments/{material.id}/{safe_name(material.display_name)}", content
                )
                file_count += 1
        for version in exported["document_versions"]:
            assert isinstance(version, models.DocumentVersion)
            if not version.docx_object_key:
                continue
            try:
                content = await storage.read(version.docx_object_key)
            except Exception:
                missing_files.append(f"document-version:{version.id}")
            else:
                archive.writestr(f"documents/{version.id}.docx", content)
                file_count += 1
        archive.writestr(
            "README.txt",
            "本压缩包是教师主动导出的账户资料。不要公开分享。\n"
            f"结构化记录：{record_count}\n附件和文档：{file_count}\n"
            f"缺失文件：{len(missing_files)}\n"
            + ("\n".join(missing_files) if missing_files else ""),
        )
    return AccountExport(
        content=buffer.getvalue(),
        filename=f"teacher-account-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip",
        record_count=record_count,
        file_count=file_count,
    )
