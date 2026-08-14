"""Expense-date validation shared by manual and model-assisted input paths."""

from __future__ import annotations

from datetime import date


class ExpenseDateValidationError(ValueError):
    """Raised when an expense date is malformed or lies in the future."""


def validate_expense_date(raw_date: str, *, current_date: date | None = None) -> str:
    """Return a normalized ISO date for an expense that has already occurred."""
    try:
        expense_date = date.fromisoformat(raw_date)
    except (TypeError, ValueError) as error:
        raise ExpenseDateValidationError("Choose a valid expense date.") from error
    if expense_date > (current_date or date.today()):
        raise ExpenseDateValidationError("Expense date cannot be in the future.")
    return expense_date.isoformat()
