"""Offline parser used for deterministic demos and parser-contract tests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Mapping

from app.services.money import MoneyValidationError, parse_paise


class DraftParseError(ValueError):
    """Raised when a text statement cannot produce a safe draft."""


@dataclass(frozen=True)
class ExpenseDraft:
    payer_id: int
    amount_paise: int
    description: str
    expense_date: str
    participant_ids: list[int]
    raw_input: str


class MockParserAdapter:
    """Parse one intentionally narrow, documented expense-statement grammar.

    Example: ``I paid ₹1200 for dinner; split equally among Asha, Rohan, and me``.
    This is deliberately offline and deterministic. A future remote adapter must return the
    same ExpenseDraft contract and is still treated as untrusted input by the route layer.
    """

    async def parse(
        self,
        raw_input: str,
        members_by_id: Mapping[int, str],
        current_user_id: int,
    ) -> ExpenseDraft:
        text = " ".join(raw_input.split())
        if not text or len(text) > 400:
            raise DraftParseError("Enter an expense statement between 1 and 400 characters.")

        amount_match = re.search(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)", text, flags=re.IGNORECASE)
        if amount_match is None:
            raise DraftParseError("Include an amount such as ₹1200.00.")
        try:
            amount_paise = parse_paise(amount_match.group(1))
        except MoneyValidationError as error:
            raise DraftParseError(str(error)) from error

        payer_match = re.match(r"(?P<payer>i|[A-Za-z][A-Za-z -]{0,50})\s+(?:paid|spent)\b", text, flags=re.IGNORECASE)
        if payer_match is None:
            raise DraftParseError("Start with a payer, for example: 'I paid ₹1200 ...'.")
        payer_id = self._resolve_name(payer_match.group("payer"), members_by_id, current_user_id)

        split_match = re.search(r"\bsplit\s+equally\s+among\s+(?P<people>.+)$", text, flags=re.IGNORECASE)
        if split_match is None:
            raise DraftParseError("Use 'split equally among Asha, Rohan, and me'.")
        people_text = split_match.group("people").rstrip(".")
        names = [
            name.strip()
            for name in re.split(r"\s*(?:,|\band\b)\s*", people_text, flags=re.IGNORECASE)
            if name.strip()
        ]
        participant_ids = [self._resolve_name(name, members_by_id, current_user_id) for name in names]
        if len(set(participant_ids)) != len(participant_ids):
            raise DraftParseError("Each participant should appear only once.")

        description_match = re.search(
            r"\bfor\s+(?P<description>.+?)(?:\s*[;,.]?\s*split\s+equally\s+among\b)",
            text,
            flags=re.IGNORECASE,
        )
        if description_match is None:
            raise DraftParseError("Include a description after 'for', for example 'for dinner'.")
        description = description_match.group("description").strip(" ;,.")
        if not description or len(description) > 120:
            raise DraftParseError("Description must contain 1 to 120 characters.")

        return ExpenseDraft(
            payer_id=payer_id,
            amount_paise=amount_paise,
            description=description,
            expense_date=date.today().isoformat(),
            participant_ids=participant_ids,
            raw_input=text,
        )

    @staticmethod
    def _resolve_name(name: str, members_by_id: Mapping[int, str], current_user_id: int) -> int:
        normalized = name.strip().casefold()
        if normalized in {"i", "me"}:
            return current_user_id
        matches = [member_id for member_id, display_name in members_by_id.items() if display_name.casefold() == normalized]
        if len(matches) != 1:
            raise DraftParseError(f"'{name.strip()}' is not a unique member of this group.")
        return matches[0]
