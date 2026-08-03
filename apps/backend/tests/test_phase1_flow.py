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
