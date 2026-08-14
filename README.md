# SplitLedger

> A deterministic group-expense ledger that turns confirmed shared expenses into clear balances and settlement suggestions. Natural-language input is an optional drafting aid, never the source of truth.

## Status

Local MVP is complete and verified with automated tests. It runs in deterministic `mock` mode by default. An optional Gemini adapter is included for natural, hurried phone-style text, but it stays behind a strict review-before-save boundary and needs local credential setup plus a live verification.

## The problem

Groups often describe expenses informally, but settlement requires exact, structured data. SplitLedger lets a group member enter an expense manually or request a text-to-draft interpretation, review the result, and save it only after validation. The app then calculates balances and suggests a compact set of transfers.

## Core principles

- Money is stored as integer paise, never floating point.
- Manual entry works without an AI provider or internet connection.
- Gemini can suggest a draft but cannot save data or calculate balances.
- Every saved expense must balance exactly across its shares.
- The project runs locally in a project-specific Python virtual environment.

## Stack

- Python and FastAPI
- SQLite locally and PostgreSQL on Vercel, both through parameterized SQL
- Server-rendered HTML, CSS, and small vanilla JavaScript enhancements
- pytest for automated checks

## Implemented features

- Local session-based login with synthetic demo users.
- Group creation and server-side membership checks.
- Manual equal-split expense entry with exact paise rounding.
- Past-or-present expense dates only, enforced in the UI and trusted save path.
- Strict ordinary-decimal amounts from ₹0.01 through ₹10,000,000.00; non-finite, scientific, and oversized values are rejected safely.
- Group history, member balances, and deterministic greedy settlement suggestions.
- Offline mock drafting plus an optional Gemini text-draft adapter for informal input, both behind an editable review-before-save boundary.
- Parameterized relational queries, password hashing, seed data, and automated tests.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` in a browser. The app creates a local SQLite database in `data/` and seeds the users `Asha`, `Rohan`, `Meera`, and `Arjun`. The password for every seeded user is `demo123`.

Run the test suite with:

```bash
.venv/bin/python -m pytest -q
```

## Safe text-draft demo

Use the mock-parser statement below after signing in as **Meera**:

```text
I paid ₹1200 for dinner; split equally among Asha, Rohan, and me
```

The parser returns an editable draft. It has no database access; the regular server-side validation and confirmation flow are still required before an expense is saved.

## Enable Gemini for natural phone-style text

The default `mock` mode works without a key and is the reliable interview fallback. To enable Gemini locally, create the ignored `.env` file and add your own key. Never paste the key into chat or commit it.

```bash
cp .env.example .env
```

Set these values in `.env`:

```text
PARSER_MODE=gemini
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

Restart the server, then try text such as:

```text
paid 450 cab w asha n rohan
yday dinner 1240, asha paid, split me rohan asha
i spent 799.5 on snacks with rohan and meera
```

Gemini receives the signed-in user, today's date, and the group's allowed display names. It must return structured JSON; the server re-validates money, dates, members, and equal splitting, and the user still reviews before confirmation. When a fact is unclear, the intended result is a clarification—not a guessed expense.

Generating a text draft performs no database write. Only the separate confirmation request can persist an expense, and that request repeats all trusted validation inside one transaction.

## Documentation

- [Project specification](docs/PROJECT_SPEC.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Test plan](docs/TEST_PLAN.md)
- [Edge-case test matrix](docs/EDGE_CASE_TEST_MATRIX.md)
- [Engineering decisions](docs/DECISIONS.md)
- [Vercel deployment guide](docs/DEPLOYMENT.md)

## Deployment status

The repository includes a Vercel ASGI entry point and persistent PostgreSQL support. Local development continues to use SQLite. A Vercel deployment must define `DATABASE_URL` and a private `SESSION_SECRET`; see the [deployment guide](docs/DEPLOYMENT.md). A public live demo should be claimed only after the persistence checklist succeeds.

## Scope boundary

SplitLedger is a portfolio project, not a payment product. It does not process money, connect to banks or UPI, store card data, use real financial data, accept voice input, or claim a globally optimal settlement count. Gemini is optional and used only to create a reviewable draft.
