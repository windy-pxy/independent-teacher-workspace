from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from httpx import ASGITransport, AsyncClient
from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from teacher_workspace.config import Settings, get_settings
from teacher_workspace.db import get_session
from teacher_workspace.main import app
from teacher_workspace.models import Base, User
from teacher_workspace.worker import run_once

PASSWORD = "fictional-multi-tenant-password"
ORIGIN = "http://test"


@pytest.fixture
async def tenant_context(
    tmp_path: Path,
) -> AsyncIterator[
    tuple[AsyncClient, AsyncClient, async_sessionmaker[AsyncSession], Settings]
]:
    url = os.environ.get("MULTITENANT_TEST_DATABASE_URL", "sqlite+aiosqlite://")
    if url.startswith("postgresql"):
        assert make_url(url).database == "teacher_multitenant_test", "Only isolated test DB allowed"
        engine = create_async_engine(url)
    else:
        engine = create_async_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        session.add_all(
            [
                User(
                    username="fictional-owner-a",
                    password_hash=PasswordHash.recommended().hash(PASSWORD),
                    ai_access_enabled=True,
                ),
                User(
                    username="fictional-owner-b",
                    password_hash=PasswordHash.recommended().hash(PASSWORD),
                    ai_access_enabled=True,
                ),
            ]
        )

    async def sessions() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    settings = Settings(
        _env_file=None,
        database_url=url,
        session_secret="fictional-multitenant-secret-long-enough",
        trusted_origins=[ORIGIN],
        local_storage_root=tmp_path / "storage",
        ai_provider="mock",
        vision_ai_provider="mock",
        worker_id="multitenant-test-worker",
    )
    app.dependency_overrides[get_session] = sessions
    app.dependency_overrides[get_settings] = lambda: settings
    transport = ASGITransport(app=app)
    try:
        async with (
            AsyncClient(transport=transport, base_url="http://test") as owner_a,
            AsyncClient(transport=transport, base_url="http://test") as owner_b,
        ):
            yield owner_a, owner_b, factory, settings
    finally:
        app.dependency_overrides.clear()
        if url.startswith("postgresql"):
            async with engine.begin() as connection:
                await connection.execute(text("TRUNCATE users, auth_rate_limits CASCADE"))
        await engine.dispose()


async def login(client: AsyncClient, username: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": ORIGIN},
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {
        "Origin": ORIGIN,
        "X-CSRF-Token": client.cookies["teacher_workspace_session_csrf"],
        "X-Expected-User-ID": response.json()["user"]["id"],
    }


async def create_core_records(client: AsyncClient, headers: dict[str, str]) -> dict[str, object]:
    subject = (
        await client.post("/api/v1/subjects", json={"name": "A专属虚构数学"}, headers=headers)
    ).json()
    student = (
        await client.post(
            "/api/v1/students",
            json={"display_name": "A专属虚构学生", "grade": "八年级"},
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
    plan = (
        await client.post(
            "/api/v1/teaching-plans",
            json={"student_subject_id": link["id"], "name": "A专属虚构计划"},
            headers=headers,
        )
    ).json()
    item = (
        await client.post(
            f"/api/v1/teaching-plans/{plan['id']}/items",
            json={
                "item_type": "KNOWLEDGE_POINT",
                "title": "A专属知识点",
                "sort_order": 1,
                "estimated_minutes": 90,
                "adjustment_reason": "虚构隔离测试",
            },
            headers=headers,
        )
    ).json()
    lesson = (
        await client.post(
            "/api/v1/lessons",
            json={
                "student_subject_id": link["id"],
                "scheduled_start": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "planned_minutes": 90,
                "unit_price_cents": 20_000,
                "lesson_type": "NEW_LESSON",
                "theme": "A专属课程标记",
                "plan_item_ids": [item["id"]],
            },
            headers=headers,
        )
    ).json()
    return {
        "subject": subject,
        "student": student,
        "link": link,
        "plan": plan,
        "item": item,
        "lesson": lesson,
    }


@pytest.mark.asyncio
async def test_two_active_teachers_cannot_cross_read_write_link_download_or_export(
    tenant_context: tuple[AsyncClient, AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    owner_a, owner_b, factory, settings = tenant_context
    headers_a = await login(owner_a, "fictional-owner-a")
    headers_b = await login(owner_b, "fictional-owner-b")
    records = await create_core_records(owner_a, headers_a)
    lesson = records["lesson"]
    link = records["link"]

    # Two devices editing the same teacher record get an explicit optimistic-lock conflict.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as device_a2:
        headers_a2 = await login(device_a2, "fictional-owner-a")
        stale_student = (
            await device_a2.get(f"/api/v1/students/{records['student']['id']}")
        ).json()
        updated_student = await owner_a.put(
            f"/api/v1/students/{records['student']['id']}",
            json={
                "display_name": "A专属虚构学生已更新",
                "grade": "八年级",
                "version": records["student"]["version"],
            },
            headers=headers_a,
        )
        assert updated_student.status_code == 200, updated_student.text
        stale_write = await device_a2.put(
            f"/api/v1/students/{records['student']['id']}",
            json={
                "display_name": "不应覆盖的新设备内容",
                "grade": "八年级",
                "version": stale_student["version"],
            },
            headers=headers_a2,
        )
        assert stale_write.status_code == 409
        assert stale_write.json()["code"] == "VERSION_CONFLICT"

    templates = (await owner_a.get("/api/v1/prompt-templates")).json()
    queued_doc = await owner_a.post(
        f"/api/v1/lessons/{lesson['id']}/documents/generate",
        json={"extra_requirements": "仅用于虚构隔离测试"},
        headers=headers_a,
    )
    assert queued_doc.status_code == 202, queued_doc.text
    assert await run_once(factory, settings)
    document = (await owner_a.get(f"/api/v1/lessons/{lesson['id']}/document")).json()

    completed = await owner_a.post(
        f"/api/v1/lessons/{lesson['id']}/complete",
        json={
            "actual_minutes": 90,
            "progress_updates": [],
            "adjustment_reason": "虚构隔离测试完成课程",
        },
        headers=headers_a,
    )
    assert completed.status_code == 200, completed.text
    feedback_response = await owner_a.post(
        f"/api/v1/lessons/{lesson['id']}/feedback/drafts",
        json={"student_performance": "A专属反馈标记"},
        headers=headers_a,
    )
    assert feedback_response.status_code == 201, feedback_response.text
    feedback = feedback_response.json()
    wrong = (
        await owner_a.post(
            "/api/v1/wrong-questions",
            json={
                "student_subject_id": link["id"],
                "mastery_status": "WEAK",
                "content": {
                    "schema_version": "1.0",
                    "question_text": "A专属错题标记：2x=4",
                    "source": "虚构测试",
                    "difficulty": "BASIC",
                    "student_answer": "x=1",
                    "correct_answer": "x=2",
                    "error_reason": "虚构计算错误",
                    "analysis": "两边同时除以2。",
                    "knowledge_points": [{"knowledge_point_id": None, "name": "方程"}],
                    "recognition_notes": "",
                },
            },
            headers=headers_a,
        )
    ).json()
    queued_set = await owner_a.post(
        "/api/v1/question-sets/generate",
        json={
            "student_subject_id": link["id"],
            "title": "A专属练习标记",
            "wrong_question_ids": [wrong["id"]],
            "knowledge_point_ids": [],
            "target_difficulty": "MEDIUM",
            "quantity": 2,
        },
        headers=headers_a,
    )
    assert queued_set.status_code == 202, queued_set.text
    assert await run_once(factory, settings)
    question_set = queued_set.json()["question_set"]

    material_response = await owner_a.post(
        "/api/v1/materials",
        data={"student_subject_id": link["id"], "purpose": "TEACHING_MATERIAL"},
        files={"file": ("A专属虚构讲义.txt", "A专属资料正文".encode(), "text/plain")},
        headers=headers_a,
    )
    assert material_response.status_code == 201, material_response.text
    material = material_response.json()
    payment = (
        await owner_a.post(
            "/api/v1/payments",
            json={
                "amount_cents": 1_000,
                "paid_at": datetime.now(UTC).isoformat(),
                "method": "虚构方式",
                "allocations": [],
            },
            headers=headers_a,
        )
    ).json()

    subject_b = (
        await owner_b.post("/api/v1/subjects", json={"name": "B专属虚构数学"}, headers=headers_b)
    ).json()
    student_b = (
        await owner_b.post(
            "/api/v1/students", json={"display_name": "B专属虚构学生"}, headers=headers_b
        )
    ).json()
    link_b = (
        await owner_b.post(
            "/api/v1/student-subjects",
            json={"student_id": student_b["id"], "subject_id": subject_b["id"]},
            headers=headers_b,
        )
    ).json()

    # Lists and dashboards may contain B's own rows, but never A's markers.
    for path in (
        "/students", "/subjects", "/student-subjects", "/teaching-plans", "/lessons",
        "/wrong-questions", "/question-sets", "/payments", "/materials",
    ):
        response = await owner_b.get(f"/api/v1{path}")
        assert response.status_code == 200, (path, response.text)
        assert "A专属" not in response.text
    assert "A专属" not in (await owner_b.get("/api/v1/dashboard")).text

    # Replacing path IDs must look indistinguishable from a missing private record.
    private_paths = (
        f"/students/{records['student']['id']}",
        f"/teaching-plans/{records['plan']['id']}",
        f"/lessons/{lesson['id']}",
        f"/lessons/{lesson['id']}/document",
        f"/lesson-documents/{document['id']}/versions",
        f"/lessons/{lesson['id']}/feedback",
        f"/lesson-feedbacks/{feedback['id']}/versions",
        f"/student-subjects/{link['id']}/mastery",
        f"/wrong-questions/{wrong['id']}",
        f"/question-sets/{question_set['id']}",
        f"/materials/{material['id']}/download",
        f"/ai-jobs/{queued_doc.json()['id']}",
    )
    for path in private_paths:
        response = await owner_b.get(f"/api/v1{path}")
        assert response.status_code == 404, (path, response.status_code, response.text)

    cross_link = await owner_b.post(
        "/api/v1/student-subjects",
        json={"student_id": student_b["id"], "subject_id": records["subject"]["id"]},
        headers=headers_b,
    )
    assert cross_link.status_code == 404
    cross_lesson = await owner_b.post(
        "/api/v1/lessons",
        json={
            "student_subject_id": link["id"],
            "scheduled_start": datetime.now(UTC).isoformat(),
            "planned_minutes": 60,
            "lesson_type": "REVIEW",
            "theme": "不应创建",
        },
        headers=headers_b,
    )
    assert cross_lesson.status_code == 404
    cross_material = await owner_b.post(
        "/api/v1/materials",
        data={"student_subject_id": link["id"], "purpose": "TEACHING_MATERIAL"},
        files={"file": ("不应保存.txt", b"blocked", "text/plain")},
        headers=headers_b,
    )
    assert cross_material.status_code == 404

    payment_b = (
        await owner_b.post(
            "/api/v1/payments",
            json={
                "amount_cents": 500,
                "paid_at": datetime.now(UTC).isoformat(),
                "method": "虚构方式",
                "allocations": [],
            },
            headers=headers_b,
        )
    ).json()
    cross_allocation = await owner_b.post(
        f"/api/v1/payments/{payment_b['id']}/allocations",
        json={"lesson_id": lesson["id"], "amount_cents": 100, "version": payment_b["version"]},
        headers=headers_b,
    )
    assert cross_allocation.status_code == 404

    template = templates[0]
    cross_template = await owner_b.put(
        f"/api/v1/prompt-templates/{template['id']}",
        json={
            "name": "不应修改",
            "system_prompt": "不应修改的系统提示词，长度足够用于严格校验。",
            "user_prompt_template": "不应修改的用户提示词，长度足够用于严格校验。",
            "change_reason": "跨账户修改应拒绝",
            "current_version_number": template["current_version_number"],
        },
        headers=headers_b,
    )
    assert cross_template.status_code == 404

    csv_export = await owner_b.get("/api/v1/billing/export.csv")
    assert csv_export.status_code == 200
    assert "A专属" not in csv_export.content.decode("utf-8-sig")
    obsidian = await owner_b.post("/api/v1/exports/obsidian.zip", headers=headers_b)
    assert obsidian.status_code == 200
    with ZipFile(BytesIO(obsidian.content)) as archive:
        exported_text = "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".md")
        )
    assert "A专属" not in exported_text

    # Failed cross-tenant attempts did not mutate or hide A's original records.
    owner_student = await owner_a.get(f"/api/v1/students/{records['student']['id']}")
    assert owner_student.status_code == 200
    owner_material = await owner_a.get(f"/api/v1/materials/{material['id']}/download")
    assert owner_material.content == "A专属资料正文".encode()
    assert (await owner_a.get("/api/v1/payments")).json()[0]["id"] == payment["id"]
    owner_b_mastery = await owner_b.get(f"/api/v1/student-subjects/{link_b['id']}/mastery")
    assert owner_b_mastery.status_code == 200
