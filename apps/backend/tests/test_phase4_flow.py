from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from teacher_workspace.config import Settings, get_settings
from teacher_workspace.db import get_session
from teacher_workspace.main import app
from teacher_workspace.models import Base, User
from teacher_workspace.worker import run_once


@pytest.fixture
async def phase4_context(
    tmp_path: Path,
) -> AsyncIterator[
    tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings]
]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session, session.begin():
        session.add(
            User(
                username="phase4-teacher",
                password_hash=PasswordHash.recommended().hash("fictional-password"),
                ai_access_enabled=True,
                ai_monthly_job_limit=100,
            )
        )
    settings = Settings(
        database_url="sqlite+aiosqlite://",
        session_secret="phase4-test-secret-that-is-long-enough",
        trusted_origins=["http://test"],
        local_storage_root=tmp_path / "storage",
        ai_provider="mock",
        vision_ai_provider="mock",
        worker_id="phase4-worker",
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory, settings
    app.dependency_overrides.clear()
    await engine.dispose()


async def login(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "phase4-teacher", "password": "fictional-password"},
        headers={"Origin": "http://test"},
    )
    assert response.status_code == 200
    csrf = client.cookies.get("teacher_workspace_session_csrf")
    assert csrf
    return {"Origin": "http://test", "X-CSRF-Token": csrf}


async def create_subject_context(
    client: AsyncClient, headers: dict[str, str]
) -> str:
    subject = (
        await client.post(
            "/api/v1/subjects",
            json={"name": "虚构数学"},
            headers=headers,
        )
    ).json()
    student = (
        await client.post(
            "/api/v1/students",
            json={"display_name": "示例学生四", "grade": "八年级"},
            headers=headers,
        )
    ).json()
    link = await client.post(
        "/api/v1/student-subjects",
        json={
            "student_id": student["id"],
            "subject_id": subject["id"],
            "current_foundation": "基础方程正在巩固",
        },
        headers=headers,
    )
    assert link.status_code == 201, link.text
    return str(link.json()["id"])


@pytest.mark.asyncio
async def test_manual_wrong_question_review_and_practice_approval(
    phase4_context: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, factory, settings = phase4_context
    headers = await login(client)
    link_id = await create_subject_context(client, headers)
    created = await client.post(
        "/api/v1/wrong-questions",
        json={
            "student_subject_id": link_id,
            "mastery_status": "WEAK",
            "content": {
                "schema_version": "1.0",
                "question_text": "解方程 2x + 3 = 11",
                "source": "虚构练习",
                "difficulty": "BASIC",
                "student_answer": "x = 7",
                "correct_answer": "x = 4",
                "error_reason": "移项符号错误",
                "analysis": "两边先减 3，再除以 2。",
                "knowledge_points": [
                    {"knowledge_point_id": None, "name": "一元一次方程"}
                ],
                "recognition_notes": "",
            },
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    wrong_question = created.json()
    assert wrong_question["status"] == "APPROVED"

    reviewed = await client.post(
        f"/api/v1/wrong-questions/{wrong_question['id']}/reviews",
        json={
            "result_level": "DEVELOPING",
            "notes": "能独立完成同类基础题",
            "version": wrong_question["version"],
        },
        headers=headers,
    )
    assert reviewed.status_code == 201, reviewed.text
    refreshed = (await client.get(f"/api/v1/wrong-questions/{wrong_question['id']}")).json()
    assert refreshed["mastery_status"] == "DEVELOPING"
    assert refreshed["review_count"] == 1

    queued = await client.post(
        "/api/v1/question-sets/generate",
        json={
            "student_subject_id": link_id,
            "title": "虚构方程巩固练习",
            "wrong_question_ids": [wrong_question["id"]],
            "knowledge_point_ids": [],
            "target_difficulty": "MEDIUM",
            "quantity": 3,
            "extra_requirements": "步骤完整",
        },
        headers=headers,
    )
    assert queued.status_code == 202, queued.text
    question_set_id = queued.json()["question_set"]["id"]
    assert await run_once(factory, settings)
    draft = (await client.get(f"/api/v1/question-sets/{question_set_id}")).json()
    assert len(draft["current_version"]["content"]["questions"]) == 3
    submitted = await client.post(
        f"/api/v1/question-sets/{question_set_id}/submit",
        json={"reason": "教师已逐题核对", "version": draft["version"]},
        headers=headers,
    )
    approved = await client.post(
        f"/api/v1/question-sets/{question_set_id}/approve",
        json={
            "reason": "答案和解析均正确",
            "version": submitted.json()["version"],
        },
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_image_upload_validates_content_and_creates_review_draft(
    phase4_context: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, factory, settings = phase4_context
    headers = await login(client)
    link_id = await create_subject_context(client, headers)
    invalid = await client.post(
        "/api/v1/wrong-questions/from-image",
        data={"student_subject_id": link_id},
        files={"image": ("question.png", b"not-an-image", "image/png")},
        headers=headers,
    )
    assert invalid.status_code == 422
    png_stub = b"\x89PNG\r\n\x1a\n" + b"fictional-image-bytes"
    uploaded = await client.post(
        "/api/v1/wrong-questions/from-image",
        data={"student_subject_id": link_id},
        files={"image": ("question.png", png_stub, "image/png")},
        headers=headers,
    )
    assert uploaded.status_code == 202, uploaded.text
    question_id = uploaded.json()["wrong_question"]["id"]
    assert await run_once(factory, settings)
    draft = (await client.get(f"/api/v1/wrong-questions/{question_id}")).json()
    assert draft["status"] == "DRAFT"
    assert draft["approved_version_number"] is None
    assert draft["current_version"]["source"] == "AI_RECOGNIZED"
