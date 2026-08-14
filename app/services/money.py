"""Exact currency parsing and equal-split calculations."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Sequence


class MoneyValidationError(ValueError):
    """Raised when an amount cannot be represented safely in paise."""


MAX_EXPENSE_RUPEES = Decimal("10000000.00")
MAX_EXPENSE_PAISE = 1_000_000_000
_GROUPED_OR_PLAIN_AMOUNT = re.compile(
    r"-?(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d{1,2})?"
)


def parse_paise(raw_amount: str) -> int:
    """Parse a human-entered INR amount into non-floating-point paise."""
    text = raw_amount.strip()
    if not text:
        raise MoneyValidationError("Enter an amount.")
    if len(text) > 32:
        raise MoneyValidationError("Amount is too long.")
    if text.startswith("₹"):
        text = text[1:].strip()
    if _GROUPED_OR_PLAIN_AMOUNT.fullmatch(text) is None:
        raise MoneyValidationError("Enter a regular amount with at most two decimal places.")
    normalized = text.replace(",", "")
    try:
        amount = Decimal(normalized)
    except InvalidOperation as error:
        raise MoneyValidationError("Enter a valid amount with at most two decimal places.") from error
    if amount <= 0:
        raise MoneyValidationError("Amount must be greater than zero.")
    if amount > MAX_EXPENSE_RUPEES:
        raise MoneyValidationError("Amount cannot exceed ₹10,000,000.00.")
    paise = amount * Decimal("100")
    if paise != paise.to_integral_value(rounding=ROUND_HALF_UP):
        raise MoneyValidationError("Amount can have at most two decimal places.")
    return int(paise)


def format_paise(amount_paise: int) -> str:
    """Format an integer paise value for display without float conversion."""
    sign = "-" if amount_paise < 0 else ""
    absolute = abs(amount_paise)
    rupees, paise = divmod(absolute, 100)
    return f"{sign}₹{rupees:,}.{paise:02d}"


def paise_input_value(amount_paise: int) -> str:
    """Return a decimal-string form value without converting money to float."""
    if amount_paise < 0:
        raise MoneyValidationError("Expense amounts cannot be negative.")
    rupees, paise = divmod(amount_paise, 100)
    return f"{rupees}.{paise:02d}"


def equal_split(amount_paise: int, participant_ids: Sequence[int]) -> dict[int, int]:
    """Split exact paise deterministically across unique participants."""
    if amount_paise <= 0:
        raise MoneyValidationError("Amount must be greater than zero.")
    if not participant_ids:
        raise MoneyValidationError("Choose at least one participant.")
    if len(set(participant_ids)) != len(participant_ids):
        raise MoneyValidationError("A participant cannot be selected more than once.")
    ordered_ids = sorted(participant_ids)
    base, remainder = divmod(amount_paise, len(ordered_ids))
    return {
        user_id: base + (1 if position < remainder else 0)
        for position, user_id in enumerate(ordered_ids)
    }
