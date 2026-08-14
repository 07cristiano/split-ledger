import pytest

from app.parsers.mock import DraftParseError, MockParserAdapter


@pytest.mark.anyio
async def test_mock_parser_returns_a_safe_draft() -> None:
    draft = await MockParserAdapter().parse(
        "I paid ₹1,200.05 for dinner; split equally among Asha, Rohan, and me",
        {1: "Asha", 2: "Rohan", 3: "Meera"},
        current_user_id=3,
    )
    assert draft.payer_id == 3
    assert draft.amount_paise == 120_005
    assert draft.description == "dinner"
    assert draft.participant_ids == [1, 2, 3]


@pytest.mark.anyio
async def test_mock_parser_rejects_unknown_member() -> None:
    with pytest.raises(DraftParseError, match="not a unique member"):
        await MockParserAdapter().parse(
            "Asha paid ₹100 for tea; split equally among Asha and Unknown",
            {1: "Asha", 2: "Rohan"},
            current_user_id=1,
        )
