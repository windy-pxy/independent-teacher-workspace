import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pwdlib import PasswordHash
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from teacher_workspace.config import Settings, get_settings
from teacher_workspace.db import get_session
from teacher_workspace.main import app
from teacher_workspace.models import Base, TeachingPlanItem, User
from teacher_workspace.phase3_service import _feedback_context
from teacher_workspace.worker import run_once


@pytest.fixture
async def phase1_context() -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session, session.begin():
        session.add(
            User(
                username="demo-teacher",
                password_hash=PasswordHash.recommended().hash("fictional-password"),
            )
        )

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        session_secret="test-session-secret-that-is-long-enough",
        trusted_origins=["http://test"],
    )
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory
    app.dependency_overrides.clear()
    await engine.dispose()


async def login(
    client: AsyncClient,
    username: str = "demo-teacher",
    password: str = "fictional-password",
) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Origin": "http://test"},
    )
    assert response.status_code == 200, response.text
    csrf = client.cookies.get("teacher_workspace_session_csrf")
    assert csrf
    return {"Origin": "http://test", "X-CSRF-Token": csrf}


@pytest.mark.asyncio
async def test_student_records_are_isolated_by_owner(
    phase1_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = phase1_context
    first_headers = await login(client)
    student = (
        await client.post(
            "/api/v1/students",
            json={"display_name": "虚构隔离学生"},
            headers=first_headers,
        )
    ).json()

    async with factory() as session, session.begin():
        await session.execute(update(User).values(is_active=False))
        session.add(
            User(
                username="second-test-teacher",
                password_hash=PasswordHash.recommended().hash("second-fictional-password"),
            )
        )
    client.cookies.clear()
    await login(client, "second-test-teacher", "second-fictional-password")

    assert (await client.get(f"/api/v1/students/{student['id']}")).status_code == 404
    assert (await client.get("/api/v1/students")).json() == []


@pytest.mark.asyncio
async def test_saved_student_survives_logout_and_fresh_browser_session(
    phase1_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, _ = phase1_context
    headers = await login(client)
    created = await client.post(
        "/api/v1/students",
        json={"display_name": "虚构持久化学生", "grade": "八年级"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    student_id = created.json()["id"]
    session_cookie = client.cookies.get("teacher_workspace_session")
    assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/students")).status_code == 401
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as fresh:
        assert session_cookie
        fresh.cookies.set("teacher_workspace_session", session_cookie)
        assert (await fresh.get("/api/v1/students")).status_code == 401
        fresh.cookies.clear()
        await login(fresh)
        restored = await fresh.get(f"/api/v1/students/{student_id}")
        assert restored.status_code == 200
        assert restored.json()["display_name"] == "虚构持久化学生"
        assert restored.json()["grade"] == "八年级"


@pytest.mark.asyncio
async def test_auth_requires_csrf_and_logout(phase1_context: tuple[AsyncClient, object]) -> None:
    client, _ = phase1_context
    unauthorized = await client.get("/api/v1/students")
    assert unauthorized.status_code == 401

    headers = await login(client)
    me = await client.get("/api/v1/auth/me")
    assert me.json()["username"] == "demo-teacher"
    missing_csrf = await client.post("/api/v1/subjects", json={"name": "数学", "description": None})
    assert missing_csrf.status_code == 403
    logout = await client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_stale_tab_cannot_write_after_account_cookie_changes(
    phase1_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = phase1_context
    first_headers = await login(client)
    first_user = (await client.get("/api/v1/auth/me")).json()
    first_headers["X-Expected-User-ID"] = first_user["id"]

    async with factory() as session, session.begin():
        second = User(
            username="second-active-teacher",
            password_hash=PasswordHash.recommended().hash("second-fictional-password"),
        )
        session.add(second)
    client.cookies.clear()
    second_headers = await login(client, "second-active-teacher", "second-fictional-password")
    second_user = (await client.get("/api/v1/auth/me")).json()
    stale_headers = {
        **second_headers,
        "X-Expected-User-ID": first_user["id"],
    }

    blocked = await client.post(
        "/api/v1/students",
        json={"display_name": "不应误存的虚构学生"},
        headers=stale_headers,
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "ACCOUNT_CONTEXT_CHANGED"
    assert (await client.get("/api/v1/students")).json() == []

    second_headers["X-Expected-User-ID"] = second_user["id"]
    saved = await client.post(
        "/api/v1/students",
        json={"display_name": "第二位教师的虚构学生"},
        headers=second_headers,
    )
    assert saved.status_code == 201


@pytest.mark.asyncio
async def test_student_plan_lesson_progress_flow(
    phase1_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = phase1_context
    headers = await login(client)
    subject = (
        await client.post(
            "/api/v1/subjects",
            json={"name": "虚构数学", "description": "仅用于自动测试"},
            headers=headers,
        )
    ).json()
    student = (
        await client.post(
            "/api/v1/students",
            json={
                "display_name": "示例学生甲",
                "grade": "八年级",
                "region": "示例地区",
                "school": "示例中学",
                "learning_characteristics": "计算认真，表达需要练习",
                "guardian_requirements": None,
                "notes": None,
            },
            headers=headers,
        )
    ).json()
    student_subject = (
        await client.post(
            "/api/v1/student-subjects",
            json={
                "student_id": student["id"],
                "subject_id": subject["id"],
                "textbook_version": "虚构版八年级",
                "current_foundation": "一次方程基础一般",
                "overall_goal": "建立代数思维",
                "stage_goal": "掌握方程应用",
                "teaching_requirements": None,
                "attention_notes": None,
            },
            headers=headers,
        )
    ).json()
    plan = (
        await client.post(
            "/api/v1/teaching-plans",
            json={
                "student_subject_id": student_subject["id"],
                "name": "虚构秋季计划",
                "description": "Phase 1 流程测试",
            },
            headers=headers,
        )
    ).json()
    item = (
        await client.post(
            f"/api/v1/teaching-plans/{plan['id']}/items",
            json={
                "parent_id": None,
                "item_type": "KNOWLEDGE_POINT",
                "title": "一元一次方程",
                "description": None,
                "sort_order": 1,
                "estimated_minutes": 120,
                "adjustment_reason": "建立首个知识点",
            },
            headers=headers,
        )
    ).json()
    start = (datetime.now(UTC) + timedelta(days=1)).replace(microsecond=0)
    lesson = (
        await client.post(
            "/api/v1/lessons",
            json={
                "student_subject_id": student_subject["id"],
                "scheduled_start": start.isoformat(),
                "planned_minutes": 120,
                "lesson_type": "NEW_LESSON",
                "theme": "方程基础",
                "special_requirements": None,
                "plan_item_ids": [item["id"]],
                "makeup_for_lesson_id": None,
            },
            headers=headers,
        )
    ).json()
    completed = await client.post(
        f"/api/v1/lessons/{lesson['id']}/complete",
        json={
            "actual_minutes": 115,
            "progress_updates": [
                {
                    "plan_item_id": item["id"],
                    "status": "IN_PROGRESS",
                    "actual_minutes_delta": 115,
                    "progress_notes": "已完成基础概念",
                }
            ],
            "adjustment_reason": "课程完成时人工确认",
        },
        headers=headers,
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "COMPLETED"
    async with factory() as session:
        stored_item = await session.scalar(select(TeachingPlanItem))
        assert stored_item is not None
        assert stored_item.status.value == "IN_PROGRESS"
        assert stored_item.actual_minutes == 115
    revisions = await client.get(f"/api/v1/teaching-plans/{plan['id']}/revisions")
    assert [row["version_number"] for row in revisions.json()] == [3, 2, 1]


@pytest.mark.asyncio
async def test_reschedule_preserves_original(phase1_context: tuple[AsyncClient, object]) -> None:
    client, _ = phase1_context
    headers = await login(client)
    subject = (
        await client.post("/api/v1/subjects", json={"name": "虚构英语"}, headers=headers)
    ).json()
    student = (
        await client.post(
            "/api/v1/students",
            json={"display_name": "示例学生乙"},
            headers=headers,
        )
    ).json()
    link = (
        await client.post(
            "/api/v1/student-subjects",
            json={"student_id": student["id"], "subject_id": subject["id"]},
            headers=headers,
        )
    ).json()
    start = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    original = (
        await client.post(
            "/api/v1/lessons",
            json={
                "student_subject_id": link["id"],
                "scheduled_start": start.isoformat(),
                "planned_minutes": 90,
                "lesson_type": "REVIEW",
                "theme": "阅读复习",
            },
            headers=headers,
        )
    ).json()
    replacement_response = await client.post(
        f"/api/v1/lessons/{original['id']}/reschedule",
        json={
            "scheduled_start": (start + timedelta(days=1)).isoformat(),
            "planned_minutes": 100,
            "reason": "示例时间冲突",
            "version": original["version"],
        },
        headers=headers,
    )
    assert replacement_response.status_code == 201, replacement_response.text
    replacement = replacement_response.json()
    assert replacement["rescheduled_from_lesson_id"] == original["id"]
    lessons = (await client.get("/api/v1/lessons")).json()
    statuses = {row["id"]: row["status"] for row in lessons}
    assert statuses[original["id"]] == "RESCHEDULED"
    assert statuses[replacement["id"]] == "PLANNED"


@pytest.mark.asyncio
async def test_mock_lesson_plan_review_and_docx_export(
    phase1_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = phase1_context
    headers = await login(client)
    subject = (
        await client.post(
            "/api/v1/subjects", json={"name": "虚构物理"}, headers=headers
        )
    ).json()
    student = (
        await client.post(
            "/api/v1/students",
            json={"display_name": "示例学生丙", "grade": "八年级"},
            headers=headers,
        )
    ).json()
    link = (
        await client.post(
            "/api/v1/student-subjects",
            json={
                "student_id": student["id"],
                "subject_id": subject["id"],
                "current_foundation": "能识别基本物理量",
                "stage_goal": "掌握速度计算",
            },
            headers=headers,
        )
    ).json()
    lesson = (
        await client.post(
            "/api/v1/lessons",
            json={
                "student_subject_id": link["id"],
                "scheduled_start": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
                "planned_minutes": 90,
                "lesson_type": "NEW_LESSON",
                "theme": "速度与路程",
            },
            headers=headers,
        )
    ).json()

    queued = await client.post(
        f"/api/v1/lessons/{lesson['id']}/documents/generate",
        json={"extra_requirements": "使用虚构题目，先讲单位换算"},
        headers=headers,
    )
    assert queued.status_code == 202, queued.text
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        session_secret="test-session-secret-that-is-long-enough",
        trusted_origins=["http://test"],
        ai_provider="mock",
        worker_id="phase2-test-worker",
    )
    assert await run_once(factory, settings)
    job = await client.get(f"/api/v1/ai-jobs/{queued.json()['id']}")
    assert job.json()["status"] == "SUCCEEDED"
    document_response = await client.get(
        f"/api/v1/lessons/{lesson['id']}/document"
    )
    assert document_response.status_code == 200, document_response.text
    document = document_response.json()
    content = document["current_version"]["content"]
    assert sum(block["minutes"] for block in content["schedule"]) == 90
    assert content["teacher_notes"][0].startswith("这是 Mock")

    submitted = await client.post(
        f"/api/v1/lesson-documents/{document['id']}/submit",
        json={"reason": "教师完成初审", "version": document["version"]},
        headers=headers,
    )
    assert submitted.json()["status"] == "PENDING_REVIEW"
    approved = await client.post(
        f"/api/v1/lesson-documents/{document['id']}/approve",
        json={"reason": "内容和答案已复核", "version": submitted.json()["version"]},
        headers=headers,
    )
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["current_version"]["status"] == "APPROVED"
    edited_content = approved.json()["current_version"]["content"]
    edited_content["teacher_notes"].append("教师已完成第二次人工复核。")
    edited = await client.put(
        f"/api/v1/lesson-documents/{document['id']}",
        json={
            "content": edited_content,
            "change_summary": "补充人工复核说明",
            "version": approved.json()["version"],
        },
        headers=headers,
    )
    resubmitted = await client.post(
        f"/api/v1/lesson-documents/{document['id']}/submit",
        json={"reason": "提交第二版", "version": edited.json()["version"]},
        headers=headers,
    )
    reapproved = await client.post(
        f"/api/v1/lesson-documents/{document['id']}/approve",
        json={"reason": "批准第二版", "version": resubmitted.json()["version"]},
        headers=headers,
    )
    assert reapproved.json()["current_version"]["status"] == "APPROVED"
    versions = await client.get(
        f"/api/v1/lesson-documents/{document['id']}/versions"
    )
    assert [item["status"] for item in versions.json()] == ["APPROVED", "SUPERSEDED"]
    exported = await client.post(
        f"/api/v1/lesson-documents/{document['id']}/export.docx",
        headers=headers,
    )
    assert exported.status_code == 200, exported.text
    assert exported.content.startswith(b"PK")
    assert "application/vnd.openxmlformats" in exported.headers["content-type"]


@pytest.mark.asyncio
async def test_feedback_approval_updates_progress_and_mastery(
    phase1_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = phase1_context
    headers = await login(client)
    subject = (
        await client.post(
            "/api/v1/subjects", json={"name": "虚构化学"}, headers=headers
        )
    ).json()
    student = (
        await client.post(
            "/api/v1/students",
            json={"display_name": "示例学生丁", "grade": "九年级"},
            headers=headers,
        )
    ).json()
    link = (
        await client.post(
            "/api/v1/student-subjects",
            json={
                "student_id": student["id"],
                "subject_id": subject["id"],
                "current_foundation": "能区分常见物质",
                "stage_goal": "掌握化学方程式基础",
            },
            headers=headers,
        )
    ).json()
    plan = (
        await client.post(
            "/api/v1/teaching-plans",
            json={
                "student_subject_id": link["id"],
                "name": "虚构化学阶段计划",
                "description": "仅用于反馈闭环测试",
            },
            headers=headers,
        )
    ).json()
    item = (
        await client.post(
            f"/api/v1/teaching-plans/{plan['id']}/items",
            json={
                "parent_id": None,
                "item_type": "KNOWLEDGE_POINT",
                "title": "化学方程式书写",
                "description": None,
                "sort_order": 1,
                "estimated_minutes": 90,
                "adjustment_reason": "建立虚构测试条目",
            },
            headers=headers,
        )
    ).json()
    lesson = (
        await client.post(
            "/api/v1/lessons",
            json={
                "student_subject_id": link["id"],
                "scheduled_start": (datetime.now(UTC) + timedelta(days=4)).isoformat(),
                "planned_minutes": 90,
                "lesson_type": "NEW_LESSON",
                "theme": "化学方程式入门",
                "plan_item_ids": [item["id"]],
            },
            headers=headers,
        )
    ).json()
    completed = await client.post(
        f"/api/v1/lessons/{lesson['id']}/complete",
        json={
            "actual_minutes": 85,
            "progress_updates": [],
            "adjustment_reason": "进度等待课后反馈审核",
        },
        headers=headers,
    )
    assert completed.status_code == 200, completed.text
    assert (await client.get("/api/v1/dashboard")).json()["pending_feedback_count"] == 1
    async with factory() as session:
        owner_id = await session.scalar(select(User.id))
        assert owner_id is not None
        _, _, _, ai_context, _ = await _feedback_context(
            session, uuid.UUID(lesson["id"]), owner_id
        )
        assert ai_context["student_alias"].startswith("学生-")
        assert student["display_name"] not in ai_context.values()

    draft = await client.post(
        f"/api/v1/lessons/{lesson['id']}/feedback/drafts",
        json={
            "actual_completed_content": "配平基础，书写规范",
            "student_performance": "概念理解较好，综合应用仍需提示",
            "weak_knowledge_points": "综合应用",
            "typical_mistakes": "漏写反应条件",
            "next_lesson_special_arrangement": "先复习配平再做变式题",
        },
        headers=headers,
    )
    assert draft.status_code == 201, draft.text
    organized = await client.post(
        f"/api/v1/lesson-feedbacks/{draft.json()['id']}/organize",
        json={"instructions": "忠于关键词，不补造事实", "version": draft.json()["version"]},
        headers=headers,
    )
    assert organized.status_code == 202, organized.text
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        session_secret="test-session-secret-that-is-long-enough",
        trusted_origins=["http://test"],
        ai_provider="mock",
        worker_id="phase3-test-worker",
    )
    assert await run_once(factory, settings)
    job = await client.get(f"/api/v1/ai-jobs/{organized.json()['id']}")
    assert job.json()["status"] == "SUCCEEDED"

    feedback = (
        await client.get(f"/api/v1/lessons/{lesson['id']}/feedback")
    ).json()
    assert feedback["current_version"]["source"] == "AI_ORGANIZED"
    assert feedback["current_version"]["content"]["plan_progress_updates"][0][
        "actual_minutes_delta"
    ] == 85
    submitted = await client.post(
        f"/api/v1/lesson-feedbacks/{feedback['id']}/submit",
        json={"reason": "教师已核对结构化反馈", "version": feedback["version"]},
        headers=headers,
    )
    assert submitted.json()["status"] == "PENDING_REVIEW"
    pending_edit = await client.post(
        f"/api/v1/lesson-feedbacks/{feedback['id']}/organize",
        json={"instructions": None, "version": submitted.json()["version"]},
        headers=headers,
    )
    assert pending_edit.status_code == 409
    approved = await client.post(
        f"/api/v1/lesson-feedbacks/{feedback['id']}/approve",
        json={"reason": "确认同步正式进度与掌握度", "version": submitted.json()["version"]},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert (await client.get("/api/v1/dashboard")).json()["pending_feedback_count"] == 0
    versions = await client.get(
        f"/api/v1/lesson-feedbacks/{feedback['id']}/versions"
    )
    assert [row["status"] for row in versions.json()] == ["APPROVED", "SUPERSEDED"]
    mastery = await client.get(f"/api/v1/student-subjects/{link['id']}/mastery")
    assert mastery.json()[0]["knowledge_point_name"] == "综合应用"
    assert mastery.json()[0]["level"] == "WEAK"
    assert mastery.json()[0]["evidence_count"] == 1
    async with factory() as session:
        stored_item = await session.get(TeachingPlanItem, uuid.UUID(item["id"]))
        assert stored_item is not None
        assert stored_item.status.value == "IN_PROGRESS"
        assert stored_item.actual_minutes == 85
    locked = await client.post(
        f"/api/v1/lessons/{lesson['id']}/feedback/drafts",
        json={"student_performance": "不应覆盖正式数据"},
        headers=headers,
    )
    assert locked.status_code == 409
