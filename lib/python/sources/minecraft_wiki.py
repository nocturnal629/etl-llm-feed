"""Fetch recent page changes from minecraft.wiki via the public MediaWiki API.

No authentication required — this is a plain read-only MediaWiki API with no
rate-limit-driven need for an API key or account.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from ..logging import get_logger
from ..schemas import WikiChange

log = get_logger(__name__)

_API_URL = "https://minecraft.wiki/api.php"
_USER_AGENT = "etl-llm-feed/1.0 (contact: etl-llm-feed project)"
_PAGE_SIZE = 50
_EXTRACT_BATCH_SIZE = 50
_TIMEOUT = 30
_MAX_PAGES = 40  # safety cap: bounds worst-case runtime within Vercel's function duration limit


def _api_get(params: dict) -> dict:
    query = {**params, "format": "json"}
    url = f"{_API_URL}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read())


def _fetch_extracts(titles: list[str]) -> dict[str, str]:
    """Batch-fetch a short plain-text intro extract per page title.

    This is the *current* article intro, not a diff of what changed in a
    given edit — good enough context for an LLM summary without the
    complexity of diffing arbitrary wikitext.
    """
    extracts: dict[str, str] = {}
    unique_titles = list(dict.fromkeys(titles))
    for i in range(0, len(unique_titles), _EXTRACT_BATCH_SIZE):
        chunk = unique_titles[i : i + _EXTRACT_BATCH_SIZE]
        payload = _api_get(
            {
                "action": "query",
                "prop": "extracts",
                "exintro": 1,
                "explaintext": 1,
                "exchars": 500,
                "titles": "|".join(chunk),
            }
        )
        pages = payload.get("query", {}).get("pages", {})
        for page in pages.values():
            title = page.get("title")
            if title:
                extracts[title] = (page.get("extract") or "").strip()
    return extracts


def _parse_change(entry: dict[str, Any], extracts: dict[str, str]) -> WikiChange | None:
    rcid = entry.get("rcid")
    title = entry.get("title")
    timestamp = entry.get("timestamp")

    if rcid is None or not title or not timestamp:
        return None

    published_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    slug = urllib.parse.quote(title.replace(" ", "_"))

    return WikiChange(
        external_id=str(rcid),
        title=title,
        url=f"https://minecraft.wiki/w/{slug}",
        published_at=published_at,
        change_type=entry.get("type") or "edit",
        user=entry.get("user") or "unknown",
        comment=entry.get("comment") or "",
        body_text=extracts.get(title, ""),
        raw_payload=entry,
    )


def fetch_changes(
    since: datetime | None = None,
    overlap_hours: int = 24,
) -> Iterator[WikiChange]:
    """Yield WikiChange records newest-first, stopping before the watermark.

    ``since`` should always be provided in practice (callers with an empty
    database should pass ``datetime.now(timezone.utc)`` rather than ``None``)
    so the cutoff bounds how far back we page. If ``since`` is genuinely
    ``None``, ``_MAX_PAGES`` still caps worst-case runtime.
    """
    cutoff: datetime | None = None
    if since is not None:
        cutoff = since.astimezone(timezone.utc) - timedelta(hours=overlap_hours)

    continue_params: dict[str, str] = {}

    for _page_num in range(_MAX_PAGES):
        params = {
            "action": "query",
            "list": "recentchanges",
            "rcprop": "title|ids|timestamp|user|comment",
            "rctype": "edit|new",
            "rcnamespace": 0,
            "rclimit": _PAGE_SIZE,
            "rcdir": "older",
            **continue_params,
        }
        log.info("fetching minecraft.wiki recent changes", extra={"continue": continue_params or None})

        payload = _api_get(params)
        entries = payload.get("query", {}).get("recentchanges", [])
        if not entries:
            break

        titles = [e["title"] for e in entries if e.get("title")]
        extracts = _fetch_extracts(titles)

        yielded = 0
        for entry in entries:
            change = _parse_change(entry, extracts)
            if change is None:
                continue
            if cutoff is not None and change.published_at <= cutoff:
                return
            yield change
            yielded += 1

        continue_params = payload.get("continue") or {}
        if not continue_params or yielded < _PAGE_SIZE:
            break
    else:
        log.warning("fetch_changes hit _MAX_PAGES safety cap", extra={"max_pages": _MAX_PAGES})
