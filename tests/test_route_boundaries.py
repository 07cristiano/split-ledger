from datetime import date, timedelta
from pathlib import Path

import httpx2 as httpx
import pytest

from app.main import create_app
from app.repositories import create_group, create_user, list_expenses, list_users


async def login(client: httpx.AsyncClient, display_name: str) -> None:
    response = await client.post(
        "/login",
        data={"display_name": display_name, "password": "demo123"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def user_ids(db_path: Path) -> dict[str, int]:
    return {str(row["display_name"]): int(row["id"]) for row in list_users(db_path)}


@pytest.mark.anyio
async def test_non_member_cannot_read_or_write_another_group(tmp_path: Path) -> None:
    db_path = tmp_path / "authorization.db"
    app = create_app(db_path, parser_mode="mock")
    ids = user_ids(db_path)
    private_group_id = create_group(db_path, "Private finance", ids["Asha"], [])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await login(client, "Meera")
        read_response = await client.get(f"/groups/{private_group_id}", follow_redirects=True)
        assert read_response.status_code == 200
        assert read_response.url.path == "/groups"
        assert "Private finance" not in read_response.text

        write_response = await client.post(
            f"/groups/{private_group_id}/expenses/new",
            data={
                "description": "Unauthorized dinner",
                "amount": "500.00",
                "expense_date": date.today().isoformat(),
                "payer_id": str(ids["Asha"]),
                "participant_ids": [str(ids["Asha"])],
            },
            follow_redirects=False,
        )
        assert write_response.status_code == 303
        assert write_response.headers["location"].startswith("/groups?error=")
    assert list_expenses(db_path, private_group_id) == []


@pytest.mark.anyio
async def test_tampered_outside_member_ids_are_rejected_on_both_save_paths(tmp_path: Path) -> None:
    db_path = tmp_path / "tampering.db"
    app = create_app(db_path, parser_mode="mock")
    ids = user_ids(db_path)
    outsider_id = create_user(db_path, "Eve", "demo123")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await login(client, "Asha")
        manual_response = await client.post(
            "/groups/1/expenses/new",
            data={
                "description": "Tampered manual expense",
                "amount": "100.00",
                "expense_date": date.today().isoformat(),
                "payer_id": str(outsider_id),
                "participant_ids": [str(ids["Asha"]), str(ids["Rohan"])],
            },
        )
        assert manual_response.status_code == 422
        assert "must belong to this group" in manual_response.text

        draft_response = await client.post(
            "/groups/1/expense-drafts/confirm",
            data={
                "raw_input": "tampered draft",
                "description": "Tampered draft expense",
                "amount": "100.00",
                "expense_date": date.today().isoformat(),
                "payer_id": str(ids["Asha"]),
                "participant_ids": [str(ids["Asha"]), str(outsider_id)],
            },
        )
        assert draft_response.status_code == 422
        assert "must belong to this group" in draft_response.text
    assert list_expenses(db_path, 1) == []


@pytest.mark.anyio
async def test_creating_a_draft_does_not_write_to_the_database(tmp_path: Path) -> None:
    db_path = tmp_path / "draft-no-write.db"
    app = create_app(db_path, parser_mode="mock")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await login(client, "Meera")
        before = list_expenses(db_path, 1)
        response = await client.post(
            "/groups/1/expense-drafts",
            data={"raw_input": "I paid ₹1200 for dinner; split equally among Asha, Rohan, and me"},
        )
        after = list_expenses(db_path, 1)

    assert response.status_code == 200
    assert "Confirm and save expense" in response.text
    assert before == after == []


@pytest.mark.anyio
async def test_future_dates_are_rejected_on_manual_and_draft_save_paths(tmp_path: Path) -> None:
    db_path = tmp_path / "future-date.db"
    app = create_app(db_path, parser_mode="mock")
    ids = user_ids(db_path)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    common = {
        "description": "Future dinner",
        "amount": "500.00",
        "expense_date": tomorrow,
        "payer_id": str(ids["Asha"]),
        "participant_ids": [str(ids["Asha"]), str(ids["Rohan"])],
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await login(client, "Asha")
        manual_response = await client.post("/groups/1/expenses/new", data=common)
        draft_response = await client.post(
            "/groups/1/expense-drafts/confirm",
            data={**common, "raw_input": "tomorrow I will pay 500 for dinner"},
        )

    assert manual_response.status_code == 422
    assert draft_response.status_code == 422
    assert "cannot be in the future" in manual_response.text
    assert "cannot be in the future" in draft_response.text
    assert list_expenses(db_path, 1) == []


@pytest.mark.anyio
async def test_non_finite_and_oversized_amounts_return_validation_errors(tmp_path: Path) -> None:
    db_path = tmp_path / "invalid-money.db"
    app = create_app(db_path, parser_mode="mock")
    ids = user_ids(db_path)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await login(client, "Asha")
        for invalid_amount in ("NaN", "Infinity", "1e3", "10000000.01", "9" * 40):
            response = await client.post(
                "/groups/1/expenses/new",
                data={
                    "description": "Invalid amount",
                    "amount": invalid_amount,
                    "expense_date": date.today().isoformat(),
                    "payer_id": str(ids["Asha"]),
                    "participant_ids": [str(ids["Asha"]), str(ids["Rohan"])],
                },
            )
            assert response.status_code == 422
    assert list_expenses(db_path, 1) == []


@pytest.mark.anyio
async def test_html_and_sql_metacharacters_remain_inert_text(tmp_path: Path) -> None:
    db_path = tmp_path / "injection.db"
    app = create_app(db_path, parser_mode="mock")
    ids = user_ids(db_path)
    descriptions = ["<script>alert(1)</script>", "Dinner'); DROP TABLE users;--"]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await login(client, "Asha")
        for description in descriptions:
            response = await client.post(
                "/groups/1/expenses/new",
                data={
                    "description": description,
                    "amount": "25.00",
                    "expense_date": date.today().isoformat(),
                    "payer_id": str(ids["Asha"]),
                    "participant_ids": [str(ids["Asha"]), str(ids["Rohan"])],
                },
                follow_redirects=False,
            )
            assert response.status_code == 303

        dashboard = await client.get("/groups/1")

    assert "<script>alert(1)</script>" not in dashboard.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in dashboard.text
    assert len(list_users(db_path)) == 4
    assert {str(row["description"]) for row in list_expenses(db_path, 1)} == set(descriptions)
