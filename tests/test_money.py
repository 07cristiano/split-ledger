import pytest

from app.services.money import MAX_EXPENSE_PAISE, MoneyValidationError, equal_split, parse_paise


def test_equal_split_allocates_every_paise_deterministically() -> None:
    shares = equal_split(100, [3, 1, 2])
    assert shares == {1: 34, 2: 33, 3: 33}
    assert sum(shares.values()) == 100


@pytest.mark.parametrize(
    "raw",
    ["", "0", "-2", "5.555", "not-money", "NaN", "Infinity", "-Infinity", "1e3", "+10", "9" * 40],
)
def test_invalid_money_is_rejected(raw: str) -> None:
    with pytest.raises(MoneyValidationError):
        parse_paise(raw)


def test_parse_paise_never_uses_float_rounding() -> None:
    assert parse_paise("1,200.05") == 120_005


def test_indian_grouping_and_maximum_amount_are_supported_exactly() -> None:
    assert parse_paise("₹1,00,000.00") == 10_000_000
    assert parse_paise("10000000.00") == MAX_EXPENSE_PAISE


def test_amount_above_documented_maximum_is_rejected() -> None:
    with pytest.raises(MoneyValidationError, match="cannot exceed"):
        parse_paise("10000000.01")
