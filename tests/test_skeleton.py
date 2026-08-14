from pathlib import Path

import httpx2 as httpx
import pytest

from app.main import create_app


@pytest.mark.anyio
async def test_health_endpoint_and_demo_login(tmp_path: Path) -> None:
    app = create_app(tmp_path / "test.db", parser_mode="mock")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/health")).json() == {"status": "ok"}
        response = await client.post(
            "/login", data={"display_name": "Asha", "password": "demo123"}, follow_redirects=False
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/groups"


@pytest.mark.anyio
async def test_invalid_login_is_rejected(tmp_path: Path) -> None:
    app = create_app(tmp_path / "test.db", parser_mode="mock")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/login", data={"display_name": "Asha", "password": "wrong"}, follow_redirects=False
        )
        assert response.status_code == 303
        assert "error=" in response.headers["location"]


@pytest.mark.anyio
async def test_member_can_create_and_review_text_draft(tmp_path: Path) -> None:
    app = create_app(tmp_path / "test.db", parser_mode="mock")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/login", data={"display_name": "Meera", "password": "demo123"}, follow_redirects=False
        )
        assert login.status_code == 303
        dashboard = await client.get("/groups/1")
        assert dashboard.status_code == 200
        assert "Weekend getaway" in dashboard.text
        review = await client.post(
            "/groups/1/expense-drafts",
            data={"raw_input": "I paid ₹1200 for dinner; split equally among Asha, Rohan, and me"},
        )
        assert review.status_code == 200
        assert "Confirm and save expense" in review.text
        confirmed = await client.post(
            "/groups/1/expense-drafts/confirm",
            data={
                "raw_input": "I paid ₹1200 for dinner; split equally among Asha, Rohan, and me",
                "description": "dinner",
                "amount": "1200.00",
                "expense_date": "2026-08-11",
                "payer_id": "3",
                "participant_ids": ["1", "2", "3"],
            },
            follow_redirects=False,
        )
        assert confirmed.status_code == 303
        updated_dashboard = await client.get("/groups/1")
        assert "dinner" in updated_dashboard.text


@pytest.mark.anyio
async def test_member_can_save_manual_expense(tmp_path: Path) -> None:
    app = create_app(tmp_path / "test.db", parser_mode="mock")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/login", data={"display_name": "Asha", "password": "demo123"})
        response = await client.post(
            "/groups/1/expenses/new",
            data={
                "description": "Taxi",
                "amount": "301.01",
                "expense_date": "2026-08-11",
                "payer_id": "1",
                "participant_ids": ["1", "2", "3"],
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        dashboard = await client.get("/groups/1")
        assert "Taxi" in dashboard.text
