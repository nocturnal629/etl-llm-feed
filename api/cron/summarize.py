"""Vercel cron function: generate daily Minecraft Wiki LLM digest from extracted items."""
from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from lib.python.db import get_conn
from lib.python.llm import generate_digest
from lib.python.logging import get_logger
from lib.python.schemas import DigestSummary

log = get_logger(__name__)


def _render_markdown(summary: DigestSummary, digest_date: date, item_count: int) -> str:
    lines = [
        f"# Minecraft Wiki Daily Digest — {digest_date}",
        f"\n**{item_count} changes** reviewed.\n",
        "## Executive Summary",
        summary.executive_summary,
        "\n## Key Themes",
        *[f"- {theme}" for theme in summary.themes],
        "\n## Top Items",
    ]
    for top_item in summary.top_items:
        lines += [f"\n### {top_item.title}", f"**Why:** {top_item.reason}"]
    return "\n".join(lines)


def _summarize(target_date: date | None = None) -> dict:
    start = time.time()
    digest_date = target_date or datetime.now(timezone.utc).date()
    since = digest_date - timedelta(days=1)

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT external_id, title, extracted
            FROM items
            WHERE published_at >= %s AND published_at < %s
              AND extracted IS NOT NULL
            ORDER BY published_at DESC
            """,
            (since, digest_date + timedelta(days=1)),
        ).fetchall()

    if not rows:
        log.info("no items for digest", extra={"date": str(digest_date)})
        return {"ok": True, "skipped": True, "reason": "no items with extraction"}

    items = [
        {"external_id": r["external_id"], "title": r["title"], "extracted": r["extracted"]}
        for r in rows
    ]

    digest = generate_digest(items)
    if digest is None:
        return {"ok": False, "error": "digest generation failed"}

    markdown = _render_markdown(digest, digest_date, len(items))

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO digests (digest_date, item_count, summary_markdown, summary_json, model)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (digest_date) DO UPDATE SET
                item_count       = EXCLUDED.item_count,
                summary_markdown = EXCLUDED.summary_markdown,
                summary_json     = EXCLUDED.summary_json,
                model            = EXCLUDED.model
            """,
            (digest_date, len(items), markdown, json.dumps(digest.model_dump()), "gemini-2.5-pro"),
        )
        conn.commit()

    runtime = round(time.time() - start, 2)
    log.info(
        "digest complete",
        extra={"date": str(digest_date), "items": len(items), "runtime_s": runtime},
    )
    return {"ok": True, "date": str(digest_date), "items": len(items), "runtime_s": runtime}


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        try:
            result = _summarize()
            body = json.dumps(result).encode()
            self.send_response(200)
        except Exception as exc:
            log.error("summarize handler error", extra={"error": str(exc)})
            body = json.dumps({"ok": False, "error": str(exc)}).encode()
            self.send_response(500)

        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        pass
