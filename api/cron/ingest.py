"""Vercel cron function: fetch Minecraft Wiki changes and run per-record LLM extraction."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# Ensure project root is on sys.path for both Vercel and local execution
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from lib.python.db import get_conn
from lib.python.llm import extract_item
from lib.python.logging import get_logger
from lib.python.sources.minecraft_wiki import fetch_changes

log = get_logger(__name__)


def _ingest() -> dict:
    start = time.time()
    fetched = inserted = updated = extracted_count = 0

    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(published_at) AS watermark FROM items WHERE source = 'minecraft_wiki'"
        ).fetchone()
        watermark = row["watermark"] if row else None
        # An empty table has no watermark to page back from; fall back to "now" so
        # the overlap window bounds the first run to recent changes instead of
        # walking the wiki's entire edit history.
        effective_since = watermark or datetime.now(timezone.utc)
        log.info("ingest started", extra={"watermark": str(watermark)})

        for item in fetch_changes(since=effective_since):
            fetched += 1
            existing = conn.execute(
                "SELECT id FROM items WHERE external_id = %s",
                (item.external_id,),
            ).fetchone()

            if existing is None:
                conn.execute(
                    """
                    INSERT INTO items (external_id, source, title, url, published_at, raw_payload)
                    VALUES (%s, 'minecraft_wiki', %s, %s, %s, %s)
                    """,
                    (
                        item.external_id,
                        item.title,
                        item.url,
                        item.published_at,
                        json.dumps(item.raw_payload),
                    ),
                )
                conn.commit()
                inserted += 1

                result = extract_item(item.title, item.body_text)
                if result:
                    conn.execute(
                        "UPDATE items SET extracted = %s, extracted_at = now() WHERE external_id = %s",
                        (json.dumps(result.model_dump()), item.external_id),
                    )
                    conn.commit()
                    extracted_count += 1
            else:
                conn.execute(
                    "UPDATE items SET raw_payload = %s WHERE external_id = %s",
                    (json.dumps(item.raw_payload), item.external_id),
                )
                conn.commit()
                updated += 1

    runtime = round(time.time() - start, 2)
    log.info(
        "ingest complete",
        extra={
            "fetched": fetched,
            "inserted": inserted,
            "updated": updated,
            "extracted": extracted_count,
            "runtime_s": runtime,
        },
    )
    return {
        "fetched": fetched,
        "inserted": inserted,
        "updated": updated,
        "extracted": extracted_count,
        "runtime_s": runtime,
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        try:
            result = _ingest()
            body = json.dumps({"ok": True, **result}).encode()
            self.send_response(200)
        except Exception as exc:
            log.error("ingest handler error", extra={"error": str(exc)})
            body = json.dumps({"ok": False, "error": str(exc)}).encode()
            self.send_response(500)

        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        pass
