# Vercel deployment

## Why local SQLite cannot be used on Vercel

SplitLedger writes a durable relational ledger. Local development uses `data/splitledger.db`, but a Vercel serverless function cannot treat its deployed project bundle as persistent writable storage. Temporary files may also disappear or differ across instances.

The supported architecture is therefore:

```text
Local development → SQLite file
Vercel function   → managed PostgreSQL through DATABASE_URL
```

Do not point Vercel at `/tmp/splitledger.db` for a portfolio demo that promises persistence.

## Files that enable Vercel

- `api/index.py` exports the FastAPI ASGI application.
- `vercel.json` routes requests to the Python serverless function.
- `app/db.py` selects SQLite or PostgreSQL and creates the matching schema.
- `psycopg[binary]` is the PostgreSQL driver.

## Required Vercel environment variables

Configure these for Production (and Preview if previews should work):

```text
APP_ENV=production
DATABASE_URL=<persistent PostgreSQL connection URL>
SESSION_SECRET=<long random private value>
SEED_DEMO_DATA=true
PARSER_MODE=mock
```

For Gemini mode, also configure:

```text
PARSER_MODE=gemini
GEMINI_API_KEY=<rotated private key>
GEMINI_MODEL=gemini-2.5-flash
```

Prefer the database provider's pooled PostgreSQL URL when it offers one for serverless applications. Never put real values into `.env.example` or Git.

Generate a session secret locally with a cryptographically secure tool, for example:

```bash
openssl rand -hex 32
```

## Deployment sequence

1. Provision a persistent managed PostgreSQL database.
2. Add its connection string as `DATABASE_URL` in Vercel project settings.
3. Add a private `SESSION_SECRET`.
4. Start with `PARSER_MODE=mock` so deployment verification is independent of Gemini.
5. Redeploy the latest Git commit.
6. Open `/health`; expect `{"status":"ok"}`.
7. Sign in with a seeded demo user and create one manual expense.
8. Reload and open the app in a new request to verify the expense persists.
9. Enable Gemini only after the deterministic flow works.

The schema uses `CREATE TABLE/INDEX IF NOT EXISTS`, and demo seeding is guarded so repeated cold starts do not duplicate the seed data. A PostgreSQL advisory transaction lock serializes the first concurrent seed attempt.

## Actionable configuration failures

On Vercel, startup intentionally fails with a clear log message when:

- `DATABASE_URL` is absent, because falling back to SQLite would be unreliable.
- `SESSION_SECRET` is absent or still uses the development fallback.
- PostgreSQL is selected but the driver is unavailable.

## Troubleshooting order

1. Read the first Python exception in the Function logs, not only the generic 500 page.
2. Confirm `DATABASE_URL` begins with `postgresql://` or `postgres://` and belongs to the correct Vercel environment.
3. Confirm the database accepts connections from the deployment and the URL includes required TLS parameters.
4. Confirm `SESSION_SECRET` is set.
5. Verify `/health` before testing login or Gemini.
6. If Gemini fails while `/health` and manual expenses work, diagnose it as a separate provider issue.

Never paste database URLs, session secrets, or API keys into issues, screenshots, chat, or logs.
