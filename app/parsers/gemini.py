"""Gemini adapter for natural-language expense drafting.

The adapter produces an untrusted ``ExpenseDraft`` only. It has no database access, and the
ordinary SplitLedger confirmation route still validates and persists every expense.
"""

from __future__ import annotations

import json
from datetime import date
from difflib import get_close_matches
from typing import Any, Mapping

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.parsers.mock import DraftParseError, ExpenseDraft
from app.services.dates import ExpenseDateValidationError, validate_expense_date
from app.services.money import MoneyValidationError, parse_paise


class GeminiDraftPayload(BaseModel):
    payer_name: str | None = None
    amount_rupees: str | int | float | None = None
    description: str | None = None
    expense_date: str | None = None
    participant_names: list[str] = Field(default_factory=list)
    split_type: str | None = None
    clarification: str | None = None


class GeminiParserAdapter:
    """Use Gemini structured JSON output for flexible, mobile-friendly expense statements."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise DraftParseError("Gemini is not configured. You can still use manual entry or mock mode.")
        if not model:
            raise DraftParseError("Set GEMINI_MODEL before enabling Gemini mode.")
        self.api_key = api_key
        self.model = model
        self.transport = transport

    async def parse(
        self,
        raw_input: str,
        members_by_id: Mapping[int, str],
        current_user_id: int,
    ) -> ExpenseDraft:
        text = " ".join(raw_input.split())
        if not text or len(text) > 400:
            raise DraftParseError("Enter an expense statement between 1 and 400 characters.")

        request_body = self._request_body(text, members_by_id, current_user_id)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=15.0) as client:
                response = await client.post(url, params={"key": self.api_key}, json=request_body)
            response.raise_for_status()
        except httpx.TimeoutException as error:
            raise DraftParseError("Gemini timed out. Please try again or use manual entry.") from error
        except httpx.HTTPStatusError as error:
            raise DraftParseError("Gemini could not create a draft. Please try again or use manual entry.") from error
        except httpx.HTTPError as error:
            raise DraftParseError("Gemini is unavailable. Please try again or use manual entry.") from error

        try:
            response_body = response.json()
        except (json.JSONDecodeError, ValueError) as error:
            raise DraftParseError("Gemini returned an unreadable draft. Please try again or use manual entry.") from error
        payload = self._parse_response(response_body)
        if payload.clarification:
            raise DraftParseError(f"I need one detail before creating a draft: {payload.clarification}")
        if payload.split_type != "equal":
            raise DraftParseError("SplitLedger currently supports equal splits only. Please say 'split equally'.")
        if not all(
            [
                payload.payer_name,
                payload.amount_rupees is not None,
                payload.description,
                payload.expense_date,
                payload.participant_names,
            ]
        ):
            raise DraftParseError("I could not identify every expense detail. Please include payer, amount, participants, and what it was for.")

        try:
            amount_paise = parse_paise(str(payload.amount_rupees))
        except MoneyValidationError as error:
            raise DraftParseError(str(error)) from error
        description = payload.description.strip()
        if not description or len(description) > 120:
            raise DraftParseError("Description must contain 1 to 120 characters.")
        try:
            expense_date = validate_expense_date(payload.expense_date)
        except ExpenseDateValidationError as error:
            raise DraftParseError(str(error)) from error

        payer_id = self._resolve_member(payload.payer_name, members_by_id, current_user_id)
        participant_ids = [
            self._resolve_member(name, members_by_id, current_user_id) for name in payload.participant_names
        ]
        if len(set(participant_ids)) != len(participant_ids):
            raise DraftParseError("Each participant should appear only once. Please review the draft.")

        return ExpenseDraft(
            payer_id=payer_id,
            amount_paise=amount_paise,
            description=description,
            expense_date=expense_date,
            participant_ids=participant_ids,
            raw_input=text,
        )

    def _request_body(
        self,
        text: str,
        members_by_id: Mapping[int, str],
        current_user_id: int,
    ) -> dict[str, Any]:
        member_names = list(members_by_id.values())
        current_user = members_by_id[current_user_id]
        today = date.today().isoformat()
        prompt = f"""You extract a draft shared-expense record for SplitLedger.

Today is {today}. The signed-in user is {current_user}. The only valid group members are: {', '.join(member_names)}.

Users may type quickly on a phone, use lowercase, shorthand, missing punctuation, or variants such as:
- "paid 450 cab w asha n rohan"
- "yday dinner 1240, asha paid, split me rohan asha"
- "i spent 799.5 on snacks with rohan and meera"

Interpret "I", "me", and "myself" as {current_user}. Resolve relative dates such as today/yesterday using today's date. The app records expenses that already happened, so a future or planned payment requires clarification and must not become a draft. Normalize a member reference only to an exact valid member name from the list. Never invent an amount, a person, a date, or a split rule. If any required detail is missing or ambiguous, return a concise clarification and leave the uncertain fields null or empty.

SplitLedger currently supports only equal splits. Return JSON only, with exactly these fields:
{{
  "payer_name": "one valid member name or null",
  "amount_rupees": "decimal string or null",
  "description": "short description or null",
  "expense_date": "YYYY-MM-DD or null",
  "participant_names": ["valid member names"],
  "split_type": "equal or null",
  "clarification": "question for the user or null"
}}

User input: {text}"""
        return {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }

    @staticmethod
    def _parse_response(response_body: dict[str, Any]) -> GeminiDraftPayload:
        try:
            parts = response_body["candidates"][0]["content"]["parts"]
            text = "".join(str(part.get("text", "")) for part in parts).strip()
            if text.startswith("```"):
                text = text.split("\n", maxsplit=1)[-1].rsplit("```", maxsplit=1)[0].strip()
            return GeminiDraftPayload.model_validate(json.loads(text))
        except (IndexError, KeyError, TypeError, json.JSONDecodeError, ValidationError) as error:
            raise DraftParseError("Gemini returned an unreadable draft. Please try again or use manual entry.") from error

    @staticmethod
    def _resolve_member(name: str, members_by_id: Mapping[int, str], current_user_id: int) -> int:
        normalized = "".join(character for character in name.casefold() if character.isalnum())
        if normalized in {"i", "me", "myself"}:
            return current_user_id
        normalized_members = {
            "".join(character for character in display_name.casefold() if character.isalnum()): member_id
            for member_id, display_name in members_by_id.items()
        }
        if normalized in normalized_members:
            return normalized_members[normalized]
        suggestions = get_close_matches(normalized, normalized_members.keys(), n=1, cutoff=0.84)
        if suggestions:
            suggestion = members_by_id[normalized_members[suggestions[0]]]
            raise DraftParseError(f"I could not match '{name}'. Did you mean '{suggestion}'? Please edit the text and retry.")
        raise DraftParseError(f"'{name}' is not a member of this group. Please check the name and retry.")
