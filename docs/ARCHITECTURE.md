# SplitLedger architecture

## 1. Design objective

The architecture optimizes for correctness, explainability, and local reliability rather than feature count. The financial ledger and settlement logic must remain deterministic even when the optional parser is unavailable or wrong.

## 2. Chosen stack

| Layer | Choice | Reason |
|---|---|---|
| Application | Python + FastAPI | Keeps the implementation in one language and provides clear request validation. |
| Persistence | SQLite locally; PostgreSQL on Vercel | Preserves zero-setup local development while providing durable storage across serverless instances. |
| Views | Server-rendered HTML/CSS with small vanilla JavaScript | Keeps the client small and avoids a separate frontend build toolchain. |
| Tests | pytest | Small, readable automated checks for business rules and routes. |
| Parser | `ParserAdapter` with mock and optional Gemini implementations | Keeps the core independent from one provider and allows an offline demo. |

## 3. Component boundaries

```text
Browser form/text input
        |
FastAPI route and request validation
        |
Service layer: authorization, business rules, draft validation
        |----------------------------|
Relational repository          ParserAdapter
        |                         |-- MockParserAdapter
Confirmed expenses             |-- GeminiParserAdapter (optional)
        |
Balance service → settlement service → template response
```

## 4. Repository layout to create during implementation

```text
app/
  main.py
  db.py
  routes/
  services/
  repositories/
  parsers/
  templates/
  static/
tests/
scripts/
docs/
```

Routes handle HTTP concerns. Services enforce authorization and invariants. Repositories contain parameterized relational queries with driver-specific placeholders and aggregation where required. The settlement service is pure Python where possible so it can be tested without a web server or database.

## 5. Money and split invariant

Represent every amount in paise as an integer. For an equal split of `A` paise among `n` people, give every person `A // n` paise and allocate the `A % n` remaining paise in a deterministic member order. The sum of shares must equal `A` exactly.

Never use binary floating point for storage or settlement calculations.

## 6. Balance and settlement algorithm

For an expense with amount `A`, credit the payer by `A` and debit each participant by their confirmed share. Aggregate these values across a group. The balance sum must be zero.

For settlement, form debtor and creditor collections of non-zero balances. Repeatedly match one debtor and one creditor by the smaller absolute balance, emit a transfer, and update both. Using heaps gives `O(p log p)` settlement time after aggregation for `p` non-zero members. The result is a valid compact plan with at most `p - 1` transfers; it is not claimed to be the global minimum-transfer solution.

## 7. Draft-parser trust boundary

```text
unstructured text
  → parser draft
  → strict schema validation
  → group-member resolution and money validation
  → user preview/edit
  → explicit confirmation
  → single database transaction
```

The parser has no database connection and no tool access. Its response is untrusted input: unknown names, invalid amounts, unsupported split types, and malformed JSON are rejected. `PARSER_MODE=mock` works without a key or network. `PARSER_MODE=gemini` sends only the submitted statement, current date, signed-in display name, and allowed group names to Gemini, which must return structured JSON. The remote provider is enabled only through project-local environment configuration.

## 8. Security and privacy baseline

- Hash passwords; never store plaintext credentials.
- Use parameterized SQL; never concatenate user input into SQL strings.
- Check group membership on every group-scoped route.
- Keep API credentials in `.env`, outside Git.
- Use synthetic demo data only.
- Do not accept payments or financial account information.

## 9. Key tradeoffs

| Decision | Chosen option | Deferred alternative |
|---|---|---|
| Frontend | Templates + vanilla JS | React/TypeScript |
| Data access | Explicit SQLite/PostgreSQL queries | ORM abstraction |

## 10. Deployment boundary

Local runs default to a project-local SQLite file. If `DATABASE_URL` is present, the database layer selects PostgreSQL and uses the same repository/business rules. Vercel refuses to fall back to SQLite because its serverless filesystem cannot provide durable shared ledger state. Production mode also requires a private session secret and enables secure session cookies.
| Split type | Equal split only | Custom/percentage/weighted split |
| Parser | Draft + validation + confirmation | Autonomous expense creation |
| Input mode | Text/manual | Voice and receipt OCR |
| Settlement | Deterministic greedy plan | Exact global optimization |
