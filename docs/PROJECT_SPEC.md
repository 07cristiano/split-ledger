# SplitLedger product specification

## 1. Product statement

SplitLedger is a local-first web application for small groups that records shared expenses, computes exact net balances, and produces settlement suggestions. A text parser may transform informal text into a reviewable draft; deterministic application logic validates and persists the final expense.

## 2. Target user and problem

The target user is a student, flatmate, or small trip group that has shared expenses but does not want to calculate balances manually. The main friction is turning a statement such as “I paid ₹1,200 for dinner with Asha, Rohan, and me” into precise payer, amount, participants, and shares.

## 3. MVP user stories

1. As an authenticated member, I can create a group and add seeded/demo members.
2. As a group member, I can create a manual equal-split expense with payer, amount, description, date, and participants.
3. As a group member, I can view only groups of which I am a member.
4. As a group member, I can view group expense history and each member's net balance.
5. As a group member, I can view a valid settlement suggestion that resolves all net balances.
6. As a group member, I can submit informal text and receive an editable expense draft before it is saved.
7. As a user, I can use the app's manual and mock-parser paths without an external API key.
8. As a configured user, I can type hurried, informal text and receive a Gemini-generated draft that I must review before saving.

## 4. Explicit non-goals

- No payments, UPI/bank integration, cards, wallets, or payment reminders.
- No receipt OCR, multiple currencies, recurring expenses, arbitrary split types, or production-scale collaboration.
- No voice input in the MVP.
- No LLM-written database records, LLM-calculated balances, or autonomous actions.
- No claim that the greedy settlement plan globally minimizes the number of transfers.

## 5. Functional acceptance criteria

| ID | Criterion |
|---|---|
| AC-01 | A manual equal-split expense is rejected unless amount is positive, every participant is a group member, and all fields are valid. |
| AC-02 | All money values are stored in integer paise, and equal-split rounding allocates every paise exactly once. |
| AC-03 | The sum of all net group balances is exactly zero after every confirmed expense. |
| AC-04 | Applying the settlement suggestions results in zero balance for every non-zero member. |
| AC-05 | A member cannot read or write data for a group they do not belong to. |
| AC-06 | Parser output is shown as an editable draft; no parsed text is saved without explicit confirmation. |
| AC-07 | A malformed parser response, unknown name, or invalid amount cannot be committed. |
| AC-08 | A seed-data demo completes in under three minutes without an API key. |
| AC-09 | An expense date must be a real date on or before the server's current local date. |
| AC-10 | An amount must use ordinary decimal notation, contain at most two decimal places, and be no greater than ₹10,000,000.00. |
| AC-11 | Producing a text draft performs no database write; only explicit confirmation can start the validated expense transaction. |

## 6. Roles and authorization

- **Authenticated user:** can create a group and see groups they belong to.
- **Group creator:** selects demo members while creating a group for the MVP.
- **Group member:** can add expenses and view history, balances, and settlement suggestions for that group.

Authorization is enforced on the server. Client-side visibility is never sufficient.

## 7. Domain model

| Table | Purpose |
|---|---|
| `users` | Local identity with display name and password hash. |
| `groups` | A named expense-sharing group and its creator. |
| `group_members` | Membership relation between users and groups. |
| `expenses` | One confirmed expense, its payer, amount in paise, date, description, and original input mode. |
| `expense_shares` | One participant's exact share of an expense in paise. |

Settlement suggestions are derived from confirmed expenses; they do not need a persisted table in the MVP.

## 8. Routes and user flow

| Route or page | Purpose |
|---|---|
| `GET /health` | Confirm the application is running. |
| `GET /groups` and `POST /groups` | List/create groups for the signed-in user. |
| `GET /groups/{group_id}` | Dashboard with history, balances, and settlement suggestions. |
| `GET/POST /groups/{group_id}/expenses/new` | Manual expense form and confirmed write. |
| `POST /groups/{group_id}/expense-drafts` | Produce an untrusted text-derived draft. |
| `POST /groups/{group_id}/expense-drafts/confirm` | Validate an edited draft and persist a confirmed expense. |

The product path is: sign in → choose group → manual entry or text draft → review/edit → confirm → dashboard.

## 9. AI-parser boundary

The parser receives only the text needed to form a draft, the current date, the signed-in display name, and allowed group display names. It returns a fixed contract: payer name, amount, description, date, participant names, split type, and a clarification when it cannot safely complete the draft. The server maps names to IDs, validates the complete draft, and requires user confirmation. `MockParserAdapter` supports tests and offline demos; `GeminiParserAdapter` is optional, configured through a local ignored `.env` file, and has no database access.

## 10. Success definition

The MVP succeeds when its local demo can use a seeded group, create a manual expense, show exact balances and settlement, exercise the mock text-draft path, and satisfy every acceptance criterion. Gemini is considered live-verified only after a local real-key test succeeds.
