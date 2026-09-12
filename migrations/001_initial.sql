-- Enable pgcrypto for gen_random_uuid() (pre-Postgres 13 fallback)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS items (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id  TEXT        UNIQUE NOT NULL,
    source       TEXT        NOT NULL,
    title        TEXT        NOT NULL,
    url          TEXT        NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    raw_payload  JSONB       NOT NULL,
    extracted    JSONB,
    extracted_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_items_source_published_at
    ON items (source, published_at DESC);

CREATE INDEX IF NOT EXISTS idx_items_extracted_at
    ON items (extracted_at);

CREATE TABLE IF NOT EXISTS digests (
    id               UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
    digest_date      DATE  NOT NULL UNIQUE,
    item_count       INT   NOT NULL,
    summary_markdown TEXT  NOT NULL,
    summary_json     JSONB NOT NULL,
    model            TEXT  NOT NULL,
    created_at       TIMESTAMPTZ DEFAULT now()
);
