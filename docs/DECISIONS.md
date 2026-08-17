# SplitLedger decision log

Each entry records the problem, alternatives, chosen tradeoff, and supporting evidence.

| ID | Decision | Choice | Reason and tradeoff |
|---|---|---|---|
| D-001 | Project name | SplitLedger | Clear, professional, pronounceable, and descriptive without presenting AI as the product. No claim is made that the name is globally unique. |
| D-002 | Primary input | Manual form first; text draft second | Manual entry guarantees a working product; natural language improves convenience but must not control money logic. |
| D-003 | Voice | Deferred stretch feature | Voice requires a separate transcription path and would increase complexity without strengthening the deterministic ledger core. |
| D-004 | Money representation | Integer paise | Exact arithmetic and clear rounding tests; avoids floating-point errors. |
| D-005 | Settlement | Greedy creditor/debtor matching | Deterministic, explainable, and `O(p log p)`; does not claim global minimum transfer count. |
| D-006 | Data access | SQLite through Python `sqlite3` and parameterized SQL | Directly supports SQL learning and local reliability; more manual than an ORM. |
| D-007 | Frontend | Templates and small vanilla JavaScript | Smaller learning curve than React/Node; lower setup risk in the current environment. |
| D-008 | Parser design | Adapter with mock mode and optional remote mode | Offline demo and tests remain reliable; provider changes do not affect business logic. |
| D-009 | Description limit | 120 characters, enforced in UI and backend | Keeps history readable while server-side validation protects direct HTTP requests that bypass HTML limits. |
| D-010 | Gemini integration | Optional JSON draft adapter, not an autonomous agent | Supports hurried, mobile-style statements while keeping Gemini outside the database and settlement path. The adapter receives minimal context, rejects malformed/unknown output, and requires user confirmation; `mock` mode remains the no-key demo fallback. |
| D-011 | Expense date boundary | Past or present dates only | SplitLedger records expenses that already happened, not scheduled payments. HTML date limits improve usability, while shared backend validation prevents bypasses and rejects future Gemini output. |
| D-012 | Amount input boundary | Ordinary decimal INR from ₹0.01 to ₹10,000,000.00 | A one-crore ceiling is far above the student/travel use case while remaining safely inside the relational integer capacity. Strict syntax rejects non-finite values, scientific notation, and excessively long input before persistence. |
| D-013 | Deployment persistence | SQLite locally; PostgreSQL through `DATABASE_URL` on Vercel | SQLite keeps local setup simple, but a serverless filesystem cannot persist a shared ledger. The repository retains explicit SQL while a small driver boundary translates placeholders and backend-specific schema/aggregation. |
| D-014 | Hurried-input interpretation | Explicit shorthand conventions before clarification | Subjectless `paid/spent`, omitted dates on completed expenses, `w/n`, and `split all N` have deterministic app-level meanings. Gemini may apply only those documented rules and must clarify remaining ambiguity; this improves phone input without allowing invented people, amounts, or conflicting split rules. |

## Name selection framework

The name was evaluated for a resume project, not for a globally verified commercial brand. Scores are on a 1-5 scale; the global-uniqueness criterion is intentionally excluded because it cannot be established without a proper external trademark/name search.

| Candidate name | Clarity 35% | Professional tone 25% | Memorability 20% | Pronunciation 10% | Avoids AI label 10% | Weighted score / 5 |
|---|---:|---:|---:|---:|---:|---:|
| SplitLedger | 5.0 | 5.0 | 4.0 | 5.0 | 5.0 | 4.80 |
| TallyCircle | 4.0 | 4.5 | 4.5 | 4.5 | 5.0 | 4.35 |
| PocketShare | 4.0 | 4.0 | 4.5 | 4.5 | 5.0 | 4.20 |
| SettleFlow | 4.0 | 4.0 | 4.5 | 4.5 | 3.0 | 4.05 |

`score = Σ(weight × criterion score)`

## Future-entry template

```text
### D-XXX: <short decision>
- Problem:
- Options considered:
- Chosen approach:
- Tradeoff accepted:
- Evidence: <test, screenshot, bug fix, or manual demo>
- How I would explain it in an interview:
```
