# SplitLedger test plan

## 1. Testing objective

Tests are not a decoration. They prove the money, authorization, and parser-boundary rules that an interviewer is likely to challenge.

## 2. Required automated tests

| Area | Test cases |
|---|---|
| Equal split | Amount divides exactly; remainder paise are assigned deterministically; shares sum to original amount. |
| Expense validation | Reject zero/negative amounts, empty participants, duplicate/unknown members, and invalid dates. |
| Date boundary | Accept past/today; reject malformed and future dates in manual, confirmation, and Gemini paths. |
| Money boundary | Reject non-finite, scientific-notation, overlong, and above-limit values without an internal error. |
| Authorization | A user cannot view or write another group's records. |
| Balance aggregation | Sum of all member balances is zero after one and multiple expenses. |
| Settlement | Every suggested transfer is positive; applying all transfers makes all balances zero; zero-balance users are excluded. |
| Parser contract | Mock and Gemini adapters return the same draft schema; malformed output and unsupported names cannot be confirmed. |
| Gemini boundary | Hurried-text prompt includes only approved member context; unknown members and provider failures are rejected without leaking the API key. |
| Parser outage | Manual entry and mock mode work without an API key or network. |
| Route behavior | Expected success, validation, authorization, and not-found responses are returned. |
| Transaction atomicity | A forced share-insert failure rolls back the expense row and every share row. |
| Injection | HTML/script content renders escaped and SQL metacharacters remain inert data. |
| Deployment configuration | Explicit test paths override environment; Vercel requires PostgreSQL and a private session secret; serverless entry/config files are verified. |

## 3. Invariants to state in an interview

1. `sum(expense_shares.amount_paise) == expenses.amount_paise`
2. `sum(group_member_net_balances) == 0`
3. Applying every settlement transfer produces a zero balance for each member.
4. A parser result is never a confirmed expense until a user reviews it and the server validates it.

## 4. Manual demo checklist

1. Start with seeded users and a group.
2. Add a manual expense whose amount does not divide equally among participants.
3. Show the exact share rounding and updated balances.
4. Show the settlement suggestion.
5. Submit a valid text draft, edit one field, then confirm it.
6. Demonstrate rejection of an unknown participant or invalid amount.
7. Repeat the text-draft path in mock mode without a key.

## 5. Definition of done for each testable slice

- The relevant automated tests pass locally.
- One invalid/edge case is visible in the UI or route response.
- The developer can explain why the test protects a real product risk.
- Test names describe behavior rather than implementation details.

The prioritized manual and automated backlog is maintained in [EDGE_CASE_TEST_MATRIX.md](EDGE_CASE_TEST_MATRIX.md).
