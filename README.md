# ETL LLM Feed

A scheduled data pipeline that automatically fetches AI/ML research papers from arXiv every 6 hours, uses Google Gemini to extract structured insights from each paper, and generates a daily digest — all served through a Next.js dashboard.

---

## What does it actually do?

Every 6 hours, the pipeline:
1. Fetches the latest papers from arXiv (cs.AI, cs.LG, cs.CL categories)
2. Stores them in a Postgres database (skipping duplicates)
3. Sends each new paper to Gemini Flash, which extracts: topics, key contribution, methodology, and a novelty score (1–5)

Every day at 09:00 UTC, a second job:
1. Collects all papers from the past 24 hours that have been analyzed
2. Sends them to Gemini Pro, which writes a digest: top themes, top 3 papers worth reading, and a one-paragraph summary
3. Saves the digest to the database

The Next.js dashboard lets you read the latest digest, browse all papers with filters, and see a chart of ingestion activity.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Vercel Cron Jobs                     │
│                                                         │
│  Every 6 hours → /api/cron/ingest (Python)              │
│  │                                                      │
│  ├── Fetch papers from arXiv Atom API (XML)             │
│  ├── Validate each paper with Pydantic                  │
│  ├── UPSERT into Postgres (dedup by arXiv ID)           │
│  └── For each new paper → Gemini Flash → store result   │
│                                                         │
│  Daily 09:00 UTC → /api/cron/summarize (Python)         │
│  │                                                      │
│  ├── Fetch yesterday's analyzed papers from Postgres    │
│  ├── Send to Gemini Pro → structured digest             │
│  └── UPSERT into digests table                          │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
               ┌─────────────────┐
               │  Neon / Supabase│
               │    Postgres     │
               │                 │
               │  items table    │
               │  digests table  │
               └─────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                  Next.js Dashboard                      │
│                                                         │
│  /              Latest digest + recent papers + chart   │
│  /items         All papers, paginated, filterable       │
│  /digests       Archive of past digests                 │
│  /api/items     JSON API (used by pages)                │
│  /api/digests   JSON API (used by pages)                │
│  /api/health    Last ingest + digest timestamps         │
└─────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | Next.js 14 (App Router) | Server components fetch DB data directly — no separate API layer needed for pages |
| Styling | Tailwind CSS | Utility classes, no design system overhead |
| Charts | Recharts | Already in the package; simple bar charts |
| ETL jobs | Python 3.12 | Best ecosystem for data pipelines |
| LLM | Google Gemini (`google-genai` SDK) | Flash model for speed/cost on per-record extraction; Pro model for quality on digests |
| Data validation | Pydantic v2 | Validates both arXiv API responses and LLM JSON outputs |
| Database | Neon or Supabase Postgres | Serverless-compatible managed Postgres |
| DB client (Python) | `psycopg[binary]` | Industry-standard async-capable Postgres driver |
| DB client (TypeScript) | `postgres` (postgres.js) | Lightweight, template-literal-based SQL for Next.js |
| Hosting | Vercel | Free tier supports Python serverless functions and cron jobs |

---

## Project Structure

```
etl-llm-feed/
│
├── api/
│   └── cron/
│       ├── ingest.py        ← Vercel function: fetch arXiv + extract with Gemini Flash
│       └── summarize.py     ← Vercel function: daily digest with Gemini Pro
│
├── lib/
│   ├── python/
│   │   ├── config.py        ← Reads DATABASE_URL and GEMINI_API_KEY from env
│   │   ├── db.py            ← Opens a fresh Postgres connection per function call
│   │   ├── logging.py       ← Structured JSON logger (stdout → Vercel captures it)
│   │   ├── schemas.py       ← Pydantic models for arXiv papers and LLM outputs
│   │   ├── llm.py           ← Gemini wrappers with retry logic
│   │   └── sources/
│   │       └── arxiv.py     ← Fetches and parses arXiv Atom XML feed
│   └── ts/
│       └── db.ts            ← Postgres.js singleton for Next.js pages
│
├── app/                     ← Next.js App Router pages
│   ├── page.tsx             ← Home: digest + chart + recent papers
│   ├── items/page.tsx       ← All papers with pagination and date filter
│   ├── digests/page.tsx     ← Digest archive
│   ├── components/
│   │   └── PapersChart.tsx  ← Recharts bar chart (client component)
│   └── api/
│       ├── items/route.ts   ← GET /api/items?page=&date=
│       ├── digests/route.ts ← GET /api/digests
│       └── health/route.ts  ← GET /api/health
│
├── migrations/
│   ├── 001_initial.sql      ← Creates items and digests tables
│   └── run.py               ← Applies all *.sql files in order
│
├── vercel.json              ← Cron schedule + Python runtime config
├── requirements.txt         ← Python dependencies
└── package.json             ← Node.js dependencies
```

---

## Database Schema

### `items` table — one row per arXiv paper

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `external_id` | TEXT UNIQUE | arXiv paper ID (e.g. `2401.12345`) — the deduplication key |
| `source` | TEXT | Always `'arxiv'` for now |
| `title` | TEXT | Paper title |
| `url` | TEXT | Link to the arXiv abstract page |
| `published_at` | TIMESTAMPTZ | When arXiv published it |
| `raw_payload` | JSONB | Full original API response, stored for replay |
| `extracted` | JSONB | Gemini's analysis: `{topics, key_contribution, methodology, novelty_score}` |
| `extracted_at` | TIMESTAMPTZ | When the LLM extraction ran |
| `created_at` | TIMESTAMPTZ | When the row was inserted |

### `digests` table — one row per day

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `digest_date` | DATE UNIQUE | The date this digest covers — also the deduplication key |
| `item_count` | INT | How many papers were analyzed |
| `summary_markdown` | TEXT | Human-readable digest (rendered on the dashboard) |
| `summary_json` | JSONB | Structured data: `{themes, top_papers, executive_summary}` |
| `model` | TEXT | Which Gemini model generated this |
| `created_at` | TIMESTAMPTZ | When the row was inserted |

---

## Setup — Local Development

### Prerequisites
- Node.js 18+
- Python 3.11+
- A Neon or Supabase Postgres database (both have free tiers)
- A Google AI Studio API key (free tier available at aistudio.google.com)

### Step 1 — Clone and install dependencies

```bash
# Install Node.js packages
npm install

# Create a Python virtual environment and install dependencies
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

### Step 2 — Configure environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
copy .env.example .env     # Windows
# cp .env.example .env     # macOS/Linux
```

Edit `.env`:
```
DATABASE_URL=postgresql://postgres.[your-project]:[password]@[host]:6543/postgres
GEMINI_API_KEY=AIza...
```

**Where to get these:**
- `DATABASE_URL`: Supabase → Project Settings → Database → Connection Pooling → Transaction mode (port 6543). Neon: Dashboard → Connection Details → Pooled connection.
- `GEMINI_API_KEY`: [Google AI Studio](https://aistudio.google.com/apikey) → Create API key.

### Step 3 — Run the database migration

```bash
python migrations/run.py
```

Expected output:
```
  Applying 001_initial.sql ... done

All 1 migration(s) applied successfully.
```

### Step 4 — Run the Next.js dev server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) — you'll see the dashboard (empty until you run the ingestion job).

### Step 5 — Trigger the pipeline manually

The cron jobs are regular Python scripts. You can run them directly:

```bash
# Ingest papers from arXiv (takes 1–3 minutes on first run)
python -c "
import sys; sys.path.insert(0, '.')
from api.cron.ingest import _ingest
print(_ingest())
"

# Generate today's digest (run after ingest)
python -c "
import sys; sys.path.insert(0, '.')
from api.cron.summarize import _summarize
print(_summarize())
"
```

Or via HTTP once deployed to Vercel:
```bash
curl https://your-app.vercel.app/api/cron/ingest
curl https://your-app.vercel.app/api/cron/summarize
```

---

## Testing

The Python ETL logic (arXiv parsing/pagination, dedup/UPSERT idempotency, LLM structured-output retry, digest rendering) is covered by `pytest`. Everything is mocked — no live database or Gemini API calls are made.

```bash
pip install -r requirements-dev.txt
pytest
```

The TypeScript side is checked with `tsc --noEmit` and `next build` (both fail the build on type errors).

---

## How Deduplication Works

The pipeline is designed to be **idempotent** — running the same job twice produces the same result.

For **ingestion**: each arXiv paper has a unique ID (e.g. `2401.12345`). The database has a `UNIQUE` constraint on `external_id`. When we insert a paper, we use `INSERT ... ON CONFLICT (external_id) DO UPDATE` — so a paper that already exists just gets its `raw_payload` refreshed, no duplicate row is created.

For **the watermark**: on each run, we read `MAX(published_at)` from the database and only fetch papers newer than that (minus a 24-hour overlap window to catch papers that appeared out of order). This stops the pipeline from re-fetching the entire arXiv history on every run.

For **digests**: the `digest_date` column has a `UNIQUE` constraint. Re-running the summarize job for the same day overwrites the existing digest row.

---

## How LLM Extraction Works

For each new paper, `lib/python/llm.py` calls Gemini Flash with this prompt (paraphrased):

> "Extract structured metadata from this paper. Title: ... Abstract: ..."

Gemini is configured to return **structured JSON** that matches this schema:

```json
{
  "topics": ["large language models", "RLHF", "alignment"],
  "key_contribution": "Introduces a new reward model training technique that...",
  "methodology": "Fine-tunes a base model using human preference data...",
  "novelty_score": 4
}
```

This uses Gemini's `response_schema` feature — the model is constrained to output valid JSON matching the schema, rather than being asked to "respond in JSON" in the prompt (which is unreliable). If the output still fails Pydantic validation, the error is sent back to the model for one retry. If it fails again, the paper is stored without extraction data (ingestion is never blocked by an LLM failure).

---

## Deployment to Vercel

### Step 1 — Push to GitHub and connect to Vercel

1. Push this repo to GitHub
2. Go to [vercel.com](https://vercel.com), import the repo
3. Vercel will auto-detect Next.js

### Step 2 — Set environment variables in Vercel

In your Vercel project → Settings → Environment Variables, add:
- `DATABASE_URL` — same Transaction Pooler URL as your `.env`
- `GEMINI_API_KEY` — your Google AI Studio key

### Step 3 — Deploy

Click Deploy. Vercel will:
- Build the Next.js app
- Install Python dependencies from `requirements.txt`
- Register the two cron jobs from `vercel.json`

### Step 4 — Run the migration against production

```bash
DATABASE_URL="your-production-url" python migrations/run.py
```

### Cron schedule

| Job | Schedule | What it does |
|-----|----------|-------------|
| `/api/cron/ingest` | Every 6 hours | Fetches new papers + LLM extraction |
| `/api/cron/summarize` | Daily at 09:00 UTC | Generates the daily digest |

You can also trigger either job manually by visiting its URL in the browser (GET request).

---

## Dashboard Pages

| Page | Description |
|------|-------------|
| `/` | Latest digest, bar chart of papers ingested per day, 10 most recent papers |
| `/items` | All papers in a table — paginated (20 per page), filterable by date. Each row shows title, topic tags, novelty score, and a link to arXiv |
| `/digests` | Archive of all generated digests. Each shows themes as chips, top papers with reasons, and the full markdown digest in a collapsible section |
| `/api/health` | JSON endpoint: `{ ok, last_ingest, last_digest }` — useful for monitoring |

---

## Structured Logging

Every cron run emits structured JSON logs to stdout, which Vercel captures in its log viewer. Example output after an ingest run:

```json
{"timestamp": "2026-07-13T09:00:01Z", "level": "INFO", "logger": "api.cron.ingest", "message": "ingest started", "watermark": "2026-07-12T22:00:00+00:00"}
{"timestamp": "2026-07-13T09:00:03Z", "level": "INFO", "logger": "lib.python.sources.arxiv", "message": "fetching arXiv page", "start": 0}
{"timestamp": "2026-07-13T09:01:45Z", "level": "INFO", "logger": "api.cron.ingest", "message": "ingest complete", "fetched": 47, "inserted": 31, "updated": 16, "extracted": 29, "runtime_s": 102.3}
```

Fields: `timestamp` (UTC ISO), `level`, `logger` (Python module path), `message`, plus any extra fields passed by that specific log call.

---

## Common Issues

**`Required environment variable 'DATABASE_URL' is not set`**
→ Make sure `.env` exists in the project root and has the correct values. The config module calls `load_dotenv()` at import time.

**`psycopg.OperationalError: connection refused`**
→ Check that your `DATABASE_URL` is the Transaction Pooler URL (port 6543), not the direct connection URL. Direct connections don't work well in serverless environments.

**Ingest runs but `extracted` is always null**
→ Check your `GEMINI_API_KEY` is valid. Look at logs for `"item extraction failed"` entries.

**Vercel cron jobs not triggering**
→ Cron jobs require a Vercel project on the Hobby plan or above. Check Vercel → your project → Settings → Cron Jobs to confirm they registered.
