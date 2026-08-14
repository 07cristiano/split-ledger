import json
from datetime import date, timedelta

import httpx
import pytest

from app.parsers.gemini import GeminiParserAdapter
from app.parsers.mock import DraftParseError


def gemini_response(payload: dict) -> dict:
    return {
        "candidates": [
            {"content": {"parts": [{"text": json.dumps(payload)}]}}
        ]
    }


@pytest.mark.anyio
async def test_gemini_parser_turns_hurried_mobile_text_into_a_safe_draft() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=gemini_response(
                {
                    "payer_name": "Meera",
                    "amount_rupees": "450",
                    "description": "cab",
                    "expense_date": "2026-08-14",
                    "participant_names": ["Meera", "Asha", "Rohan"],
                    "split_type": "equal",
                    "clarification": None,
                }
            ),
        )

    adapter = GeminiParserAdapter(
        api_key="test-key",
        model="gemini-test",
        transport=httpx.MockTransport(handler),
    )
    draft = await adapter.parse(
        "paid 450 cab w asha n rohan",
        {1: "Asha", 2: "Rohan", 3: "Meera"},
        current_user_id=3,
    )

    assert draft.payer_id == 3
    assert draft.amount_paise == 45_000
    assert draft.description == "cab"
    assert draft.participant_ids == [3, 1, 2]
    assert "gemini-test:generateContent" in captured["url"]
    prompt = captured["body"]["contents"][0]["parts"][0]["text"]
    assert "signed-in user is Meera" in prompt
    assert "only valid group members are: Asha, Rohan, Meera" in prompt


@pytest.mark.anyio
async def test_gemini_parser_rejects_an_unknown_member_instead_of_guessing() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=gemini_response(
                {
                    "payer_name": "Meera",
                    "amount_rupees": "80",
                    "description": "tea",
                    "expense_date": "2026-08-14",
                    "participant_names": ["Meera", "Asha", "Rohit"],
                    "split_type": "equal",
                    "clarification": None,
                }
            ),
        )

    adapter = GeminiParserAdapter(
        api_key="test-key",
        model="gemini-test",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DraftParseError, match="not a member of this group"):
        await adapter.parse(
            "meera paid 80 tea w asha and rohit",
            {1: "Asha", 2: "Rohan", 3: "Meera"},
            current_user_id=3,
        )


@pytest.mark.anyio
@pytest.mark.parametrize("status_code", [401, 429, 503])
async def test_gemini_parser_exposes_provider_failure_without_leaking_key(status_code: int) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "unavailable"}})

    adapter = GeminiParserAdapter(
        api_key="very-secret-key",
        model="gemini-test",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DraftParseError, match="could not create a draft") as error:
        await adapter.parse(
            "paid 450 cab w asha n rohan",
            {1: "Asha", 2: "Rohan", 3: "Meera"},
            current_user_id=3,
        )
    assert "very-secret-key" not in str(error.value)


@pytest.mark.anyio
async def test_gemini_parser_handles_non_json_success_response_safely() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>temporary proxy page</html>")

    adapter = GeminiParserAdapter(
        api_key="test-key",
        model="gemini-test",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DraftParseError, match="unreadable draft"):
        await adapter.parse(
            "paid 450 cab w asha n rohan",
            {1: "Asha", 2: "Rohan", 3: "Meera"},
            current_user_id=3,
        )


@pytest.mark.anyio
async def test_gemini_parser_handles_timeout_safely() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow provider", request=request)

    adapter = GeminiParserAdapter(
        api_key="test-key",
        model="gemini-test",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DraftParseError, match="timed out"):
        await adapter.parse(
            "paid 450 cab w asha n rohan",
            {1: "Asha", 2: "Rohan", 3: "Meera"},
            current_user_id=3,
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response_body",
    [
        {},
        {"candidates": []},
        {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]},
    ],
)
async def test_gemini_parser_rejects_malformed_structured_output(response_body: dict) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_body)

    adapter = GeminiParserAdapter(
        api_key="test-key",
        model="gemini-test",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DraftParseError, match="unreadable draft"):
        await adapter.parse(
            "paid 450 cab w asha n rohan",
            {1: "Asha", 2: "Rohan", 3: "Meera"},
            current_user_id=3,
        )


@pytest.mark.anyio
async def test_gemini_parser_rejects_future_date_from_model() -> None:
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=gemini_response(
                {
                    "payer_name": "Meera",
                    "amount_rupees": "450",
                    "description": "planned cab",
                    "expense_date": tomorrow,
                    "participant_names": ["Meera", "Asha", "Rohan"],
                    "split_type": "equal",
                    "clarification": None,
                }
            ),
        )

    adapter = GeminiParserAdapter(
        api_key="test-key",
        model="gemini-test",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DraftParseError, match="cannot be in the future"):
        await adapter.parse(
            "tomorrow I will pay 450 for a cab with Asha and Rohan",
            {1: "Asha", 2: "Rohan", 3: "Meera"},
            current_user_id=3,
        )


@pytest.mark.anyio
async def test_gemini_parser_rejects_unsupported_split_and_clarification() -> None:
    responses = iter(
        [
            {
                "payer_name": "Meera",
                "amount_rupees": "450",
                "description": "cab",
                "expense_date": date.today().isoformat(),
                "participant_names": ["Meera", "Asha"],
                "split_type": "percentage",
                "clarification": None,
            },
            {
                "payer_name": "Meera",
                "amount_rupees": "450",
                "description": None,
                "expense_date": date.today().isoformat(),
                "participant_names": ["Meera", "Asha"],
                "split_type": "equal",
                "clarification": "What was the expense for?",
            },
        ]
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=gemini_response(next(responses)))

    adapter = GeminiParserAdapter(
        api_key="test-key",
        model="gemini-test",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DraftParseError, match="equal splits only"):
        await adapter.parse(
            "split 70 30",
            {1: "Asha", 3: "Meera"},
            current_user_id=3,
        )
    with pytest.raises(DraftParseError, match="What was the expense for"):
        await adapter.parse(
            "paid 450 with asha",
            {1: "Asha", 3: "Meera"},
            current_user_id=3,
        )


def test_gemini_parser_requires_a_local_key() -> None:
    with pytest.raises(DraftParseError, match="not configured"):
        GeminiParserAdapter(api_key="", model="gemini-test")
