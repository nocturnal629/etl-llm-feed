# Project Brief: Scheduled ETL + LLM-Summarized Data Feed

## Customize before pasting
Before sending this to Cursor, replace the `{{DOMAIN}}` placeholders with your chosen data source. The example below uses **arXiv AI/ML papers**, but anything with a public API or scrapeable feed works: GitHub trending repos, HackerNews, crypto markets, job postings, etc. Adjust the schema in the Data Model section to match your source.

---

## Project Overview

Build a production-quality scheduled ETL pipeline that ingests data from `{{DOMAIN}}`, stores it in Postgres with proper deduplication, runs LLM-powered summarization over new records, and serves the results through a Next.js dashboard hosted on Vercel.

The goal is to practice the unglamorous-but-essential parts of data engineering: idempotency, deduplication, schema evolution, structured LLM outputs, and observability — not to build a flashy UI.

**Default domain (arXiv AI/ML papers):**
- Pull recent papers from arXiv API (cs.AI, cs.LG, cs.CL categories)
- Run every 6 hours
- Daily LLM digest summarizing the day's most interesting papers

## Tech Stack

- **Language:** Python 3.11+ for ETL and LLM logic; TypeScript for frontend
- **Frontend:** Next.js 14 (App Router) on Vercel
- **Backend ETL:** Python functions deployed as Vercel Functions, triggered by Vercel Cron
- **Database:** Neon Postgres (or Supabase Postgres) — use `psycopg[binary]` or `asyncpg`
- **LLM:** Anthropic API (`anthropic` Python SDK) for summarization. Use Claude Haiku for per-record extraction (cheap, fast) and Claude Sonnet for the daily digest (higher quality)
- **Validation:** Pydantic v2 for all structured data — both source records and LLM outputs
- **Migrations:** Plain SQL files run via a small script (no heavy ORM); avoid Alembic for this scope
- **Charts:** Recharts for the dashboard
- **Logging:** Structured JSON logs (stdout); Vercel will capture them

## Architecture

```
Vercel Cron (every 6h)
    └─> /api/cron/ingest (Python)
            ├─> Fetch from {{DOMAIN}} API
            ├─> Validate with Pydantic
            ├─> Dedupe against Postgres (UPSERT on external_id)
            └─> Insert new records

Vercel Cron (daily, e.g. 09:00 UTC)
    └─> /api/cron/summarize (Python)
            ├─> Fetch new records since last digest
            ├─> Per-record LLM extraction (Haiku) → structured fields
            ├─> Roll up into daily digest (Sonnet) → markdown + JSON
            └─> Store digest in Postgres

Next.js App (Vercel)
    ├─> / → latest digest + recent items
    ├─> /items → paginated table of all records
    ├─> /digests → archive of past digests
    └─> /api/items, /api/digests (TypeScript route handlers reading from Postgres)
```

## Data Model

Two main tables. Use UUIDs for primary keys, timestamps in UTC.

**`items`** — one row per ingested record
- `id` UUID PK
- `external_id` TEXT UNIQUE NOT NULL — the source's canonical ID (e.g. arXiv ID); UPSERT key
- `source` TEXT NOT NULL — e.g. `'arxiv'`
- `title` TEXT NOT NULL
- `url` TEXT NOT NULL
- `published_at` TIMESTAMPTZ NOT NULL
- `raw_payload` JSONB NOT NULL — full source response, for replay
- `extracted` JSONB — LLM-extracted structured fields (filled in by summarize job)
- `extracted_at` TIMESTAMPTZ
- `created_at` TIMESTAMPTZ DEFAULT now()
- Index on `(source, published_at DESC)` and `(extracted_at)` for finding unprocessed rows

**`digests`** — one row per daily summary
- `id` UUID PK
- `digest_date` DATE NOT NULL UNIQUE
- `item_count` INT NOT NULL
- `summary_markdown` TEXT NOT NULL — human-readable digest
- `summary_json` JSONB NOT NULL — structured digest (themes, top items, etc.)
- `model` TEXT NOT NULL — which LLM produced this
- `created_at` TIMESTAMPTZ DEFAULT now()

## Pipeline Requirements

### Ingestion (`/api/cron/ingest`)
- Must be **idempotent**: re-running the same cron tick produces zero new rows
- Use `INSERT ... ON CONFLICT (external_id) DO UPDATE SET raw_payload = EXCLUDED.raw_payload` so updates to source records (e.g. arXiv paper revisions) are reflected
- Handle pagination — fetch until we hit records older than the most recent `published_at` in the DB (plus a safety overlap window of e.g. 24h)
- Log: records fetched, records inserted, records updated, records skipped, runtime

### Per-record extraction (run inside ingest, or as a separate step)
- For each new item, call Haiku with a strict Pydantic schema: e.g. `{topics: list[str], key_contribution: str, methodology: str, novelty_score: int (1-5)}`
- Use Anthropic's tool-use / structured output approach — do NOT parse free-text JSON from prose
- Store the result in `items.extracted`
- If LLM call fails, log and skip — don't block ingestion

### Daily digest (`/api/cron/summarize`)
- Pull all items where `published_at >= today - 1 day` AND `extracted IS NOT NULL`
- Send to Sonnet with a prompt that asks for: top 3-5 themes of the day, top 3 individual papers worth reading, one-paragraph executive summary
- Output must be Pydantic-validated structured JSON, plus a rendered markdown version
- UPSERT into `digests` on `digest_date` so re-runs are safe

### Structured LLM outputs
- Define Pydantic models for every LLM response shape
- Use Anthropic tool-use to enforce schemas (don't rely on "respond in JSON" prompting alone)
- On validation failure, retry once with the validation error appended to the prompt; if it fails again, log and move on

## Project Structure

```
.
├── api/
│   └── cron/
│       ├── ingest.py          # Vercel Python function
│       └── summarize.py       # Vercel Python function
├── lib/
│   ├── python/
│   │   ├── __init__.py
│   │   ├── db.py              # Connection pool, query helpers
│   │   ├── sources/
│   │   │   ├── __init__.py
│   │   │   └── arxiv.py       # Source-specific fetch + parse
│   │   ├── llm.py             # Anthropic client wrappers
│   │   ├── schemas.py         # Pydantic models (sources + LLM outputs)
│   │   └── logging.py         # Structured JSON logger
│   └── ts/
│       └── db.ts              # TypeScript Postgres client for Next.js routes
├── app/                        # Next.js App Router
│   ├── page.tsx               # Dashboard home
│   ├── items/page.tsx
│   ├── digests/page.tsx
│   └── api/
│       ├── items/route.ts
│       └── digests/route.ts
├── migrations/
│   ├── 001_initial.sql
│   └── run.py                 # Simple migration runner
├── vercel.json                # Cron config
├── requirements.txt
├── package.json
└── README.md
```

## `vercel.json` (cron config)

```json
{
  "crons": [
    { "path": "/api/cron/ingest", "schedule": "0 */6 * * *" },
    { "path": "/api/cron/summarize", "schedule": "0 9 * * *" }
  ]
}
```

## Development Phases

Build this in order. Don't skip ahead — each phase should be working and committed before moving on.

**Phase 1 — Foundation**
1. Set up Next.js project, install Python deps, configure Vercel
2. Create Neon DB, write `001_initial.sql`, write migration runner
3. Implement `lib/python/db.py` with a connection helper that works in serverless (open + close per invocation, no long-lived pool)
4. Implement structured logging

**Phase 2 — Ingestion**
1. Implement `lib/python/sources/arxiv.py` — fetch + parse + Pydantic-validate
2. Implement `api/cron/ingest.py` with idempotent UPSERT
3. Manually trigger via curl, verify dedup works on second run
4. Deploy to Vercel and verify the cron registers

**Phase 3 — LLM extraction**
1. Define Pydantic schemas for per-item extraction
2. Implement `lib/python/llm.py` with tool-use-based structured output and retry-on-validation-failure
3. Wire extraction into the ingest flow
4. Backfill any existing items missing `extracted`

**Phase 4 — Daily digest**
1. Implement `api/cron/summarize.py`
2. Verify idempotency (re-running same day produces same digest row)
3. Manually trigger and inspect output

**Phase 5 — Frontend**
1. Build `/` showing latest digest in markdown + counts
2. Build `/items` with pagination and a filter by date
3. Build `/digests` archive
4. Keep styling minimal — Tailwind defaults, no design system

**Phase 6 — Polish**
1. Add a `/api/health` endpoint reporting last successful ingest + summarize times
2. Add basic error tracking (just log to stdout with severity)
3. Write README with setup instructions

## Coding Standards

- Python: type hints everywhere, `ruff` + `ruff format`, no `Any` unless justified in a comment
- TypeScript: strict mode, no `any`
- All env vars accessed through a single `config` module that fails loudly on missing values
- All DB writes inside transactions
- All external API calls have explicit timeouts and a single retry with backoff
- No silent excepts — log and re-raise, or log and explicitly continue with a reason
- Commit messages: conventional commits (`feat:`, `fix:`, `chore:`)

## Working Style Preferences

- **Ask before assuming.** If a design decision is ambiguous (which source field maps to which column, what to do on partial failure, how to handle rate limits), ask me rather than picking one
- **Verify against source files before editing.** Don't make changes based on inferred state — open the file, confirm, then edit
- **Concise scoping discussions before implementation.** When starting a new phase, summarize the plan in 3-5 bullets and wait for confirmation before generating code
- **Minimal, focused outputs.** Don't add features I didn't ask for. Don't generate boilerplate beyond what the phase requires
- **Flag uncertainty.** If you're not sure whether an API behaves a certain way or a library supports something, say so rather than guessing

## Constraints to Watch

- Vercel Python functions have a **max duration of 60s** on Hobby, 300s on Pro — ingest and summarize jobs must stay within that. If a run might exceed it, design for resumability (process in batches, store cursor in DB)
- Vercel Cron only triggers up to 1× per minute on Hobby — fine for this project
- Anthropic API has rate limits — handle 429s with exponential backoff
- Neon free tier has connection limits — use short-lived connections, not pools, in serverless

## Deliverable for Phase 1

When you've finished Phase 1, show me:
1. The `001_initial.sql` migration
2. The output of running `python migrations/run.py` against a fresh DB
3. The `lib/python/db.py` implementation
4. A test invocation showing structured logs

Then wait for me to confirm before starting Phase 2.

---

**Start with Phase 1, Step 1.** Walk me through the proposed file additions before generating them.
