from collections.abc import AsyncIterator
from datetime import UTC, datetime
from io import BytesIO

import pytest
from httpx import ASGITransport, AsyncClient
from openpyxl import load_workbook
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from teacher_workspace.config import Settings, get_settings
from teacher_workspace.db import get_session
from teacher_workspace.main import app
from teacher_workspace.models import Base, User
from teacher_workspace.phase5_service import calculated_receivable_cents


@pytest.fixture
async def phase5_context() -> AsyncIterator[AsyncClient]:
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
                username="phase5-teacher",
                password_hash=PasswordHash.recommended().hash("fictional-password"),
            )
        )
    settings = Settings(
        database_url="sqlite+aiosqlite://",
        session_secret="phase5-test-secret-that-is-long-enough",
        trusted_origins=["http://test"],
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    await engine.dispose()


async def login(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "phase5-teacher", "password": "fictional-password"},
        headers={"Origin": "http://test"},
    )
    assert response.status_code == 200
    csrf = client.cookies.get("teacher_workspace_session_csrf")
    assert csrf
    return {"Origin": "http://test", "X-CSRF-Token": csrf}


async def create_lesson(client: AsyncClient, headers: dict[str, str]) -> dict[str, object]:
    subject = (
        await client.post(
            "/api/v1/subjects", json={"name": "虚构数学"}, headers=headers
        )
    ).json()
    student = (
        await client.post(
            "/api/v1/students",
            json={"display_name": "=虚构收费学生", "grade": "九年级"},
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
    lesson_response = await client.post(
        "/api/v1/lessons",
        json={
            "student_subject_id": link["id"],
            "scheduled_start": datetime.now(UTC).isoformat(),
            "planned_minutes": 90,
            "unit_price_cents": 20_000,
            "lesson_type": "EXERCISE",
            "theme": "+虚构收费流程测试",
        },
        headers=headers,
    )
    assert lesson_response.status_code == 201, lesson_response.text
    return lesson_response.json()


def test_hourly_price_rounds_to_nearest_cent_half_up() -> None:
    assert calculated_receivable_cents(20_000, 100) == 33_333
    assert calculated_receivable_cents(1, 30) == 1


@pytest.mark.asyncio
async def test_billing_payment_allocation_summary_and_void(
    phase5_context: AsyncClient,
) -> None:
    client = phase5_context
    headers = await login(client)
    lesson = await create_lesson(client, headers)
    assert lesson["receivable_cents"] == 30_000
    completed_response = await client.post(
        f"/api/v1/lessons/{lesson['id']}/complete",
        json={
            "actual_minutes": 100,
            "progress_updates": [],
            "adjustment_reason": "虚构收费测试完成课程",
        },
        headers=headers,
    )
    assert completed_response.status_code == 200, completed_response.text
    completed = completed_response.json()
    assert completed["receivable_cents"] == 33_333

    overridden_response = await client.post(
        f"/api/v1/lessons/{lesson['id']}/receivable-override",
        json={
            "receivable_cents": 35_000,
            "reason": "虚构套餐价格调整",
            "version": completed["version"],
        },
        headers=headers,
    )
    assert overridden_response.status_code == 200
    overridden = overridden_response.json()
    reset_response = await client.post(
        f"/api/v1/lessons/{lesson['id']}/receivable-reset",
        json={"reason": "恢复按实际分钟计费", "version": overridden["version"]},
        headers=headers,
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["receivable_cents"] == 33_333

    paid_at = datetime.now(UTC).isoformat()
    payment_response = await client.post(
        "/api/v1/payments",
        json={
            "amount_cents": 40_000,
            "paid_at": paid_at,
            "method": "微信",
            "reference": "fictional-transaction",
            "allocations": [],
        },
        headers=headers,
    )
    assert payment_response.status_code == 201, payment_response.text
    payment = payment_response.json()
    allocation_response = await client.post(
        f"/api/v1/payments/{payment['id']}/allocations",
        json={
            "lesson_id": lesson["id"],
            "amount_cents": 33_333,
            "version": payment["version"],
        },
        headers=headers,
    )
    assert allocation_response.status_code == 201, allocation_response.text
    assert allocation_response.json()["unallocated_cents"] == 6_667
    billing = (await client.get("/api/v1/billing/lessons")).json()
    assert billing[0]["payment_status"] == "PAID"
    assert billing[0]["outstanding_cents"] == 0

    second_response = await client.post(
        "/api/v1/payments",
        json={
            "amount_cents": 1_000,
            "paid_at": paid_at,
            "method": "现金",
            "allocations": [
                {"lesson_id": lesson["id"], "amount_cents": 1_000}
            ],
        },
        headers=headers,
    )
    second = second_response.json()
    assert (await client.get("/api/v1/billing/lessons")).json()[0][
        "payment_status"
    ] == "OVERPAID"
    voided = await client.post(
        f"/api/v1/payments/{second['id']}/void",
        json={"reason": "虚构重复收款冲销", "version": second["version"]},
        headers=headers,
    )
    assert voided.status_code == 200
    assert (await client.get("/api/v1/billing/lessons")).json()[0][
        "payment_status"
    ] == "PAID"

    summary = (await client.get("/api/v1/billing/summary")).json()
    assert summary["receivable_cents"] == 33_333
    assert summary["allocated_cents"] == 33_333
    assert summary["received_cents"] == 40_000
    dashboard = (await client.get("/api/v1/dashboard")).json()
    assert dashboard["month_receivable_cents"] == 33_333
    assert dashboard["month_received_cents"] == 40_000
    assert dashboard["month_outstanding_cents"] == 0


@pytest.mark.asyncio
async def test_billing_exports_open_and_neutralize_spreadsheet_formulas(
    phase5_context: AsyncClient,
) -> None:
    client = phase5_context
    headers = await login(client)
    await create_lesson(client, headers)
    csv_response = await client.get("/api/v1/billing/export.csv")
    assert csv_response.status_code == 200
    assert csv_response.content.startswith(b"\xef\xbb\xbf")
    csv_text = csv_response.content.decode("utf-8-sig")
    assert "'=虚构收费学生" in csv_text
    assert "'+虚构收费流程测试" in csv_text

    xlsx_response = await client.get("/api/v1/billing/export.xlsx")
    assert xlsx_response.status_code == 200
    workbook = load_workbook(BytesIO(xlsx_response.content), data_only=False)
    sheet = workbook["课时收费"]
    assert sheet["B2"].value == "'=虚构收费学生"
    assert sheet["D2"].value == "'+虚构收费流程测试"
    assert sheet["H2"].number_format == "¥#,##0.00"
