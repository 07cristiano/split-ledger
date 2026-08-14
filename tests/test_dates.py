from datetime import date, timedelta

import pytest

from app.services.dates import ExpenseDateValidationError, validate_expense_date


def test_today_and_past_expense_dates_are_accepted() -> None:
    today = date(2026, 8, 14)
    assert validate_expense_date("2026-08-14", current_date=today) == "2026-08-14"
    assert validate_expense_date("2026-08-13", current_date=today) == "2026-08-13"


def test_future_expense_date_is_rejected() -> None:
    today = date.today()
    tomorrow = (today + timedelta(days=1)).isoformat()
    with pytest.raises(ExpenseDateValidationError, match="cannot be in the future"):
        validate_expense_date(tomorrow, current_date=today)


@pytest.mark.parametrize("raw_date", ["", "not-a-date", "2026-02-30", "2027-02-29"])
def test_invalid_calendar_date_is_rejected(raw_date: str) -> None:
    with pytest.raises(ExpenseDateValidationError, match="valid expense date"):
        validate_expense_date(raw_date, current_date=date(2027, 3, 1))


def test_valid_leap_day_is_accepted() -> None:
    assert validate_expense_date("2028-02-29", current_date=date(2028, 3, 1)) == "2028-02-29"
