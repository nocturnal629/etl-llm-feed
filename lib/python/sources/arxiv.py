"""Fetch and parse arXiv papers from the Atom API."""
from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Iterator

from ..logging import get_logger
from ..schemas import ArxivPaper

log = get_logger(__name__)

_ATOM_NS = "http://www.w3.org/2005/Atom"
_BASE_URL = "http://export.arxiv.org/api/query"
_CATEGORIES = "cat:cs.AI OR cat:cs.LG OR cat:cs.CL"
_PAGE_SIZE = 50
_TIMEOUT = 30
_MAX_PAGES = 100  # safety cap: bounds worst-case runtime within Vercel's function duration limit


def _extract_arxiv_id(id_url: str) -> str:
    # "http://arxiv.org/abs/2401.12345v1" → "2401.12345"
    raw = id_url.rstrip("/").split("/")[-1]
    return raw.rsplit("v", 1)[0] if "v" in raw else raw


def _parse_entry(entry: ET.Element) -> ArxivPaper | None:
    ns = {"a": _ATOM_NS}
    id_el = entry.find("a:id", ns)
    title_el = entry.find("a:title", ns)
    summary_el = entry.find("a:summary", ns)
    published_el = entry.find("a:published", ns)

    if id_el is None or title_el is None or published_el is None:
        return None

    id_url = (id_el.text or "").strip()
    external_id = _extract_arxiv_id(id_url)
    title = " ".join((title_el.text or "").split())
    abstract = " ".join((summary_el.text or "").split()) if summary_el is not None else ""
    published_at = datetime.fromisoformat((published_el.text or "").replace("Z", "+00:00"))

    authors = [
        name.text.strip()
        for author in entry.findall("a:author", ns)
        for name in author.findall("a:name", ns)
        if name.text
    ]
    categories = [
        cat.get("term", "")
        for cat in entry.findall("a:category", ns)
        if cat.get("term")
    ]

    raw_payload = {
        "id": id_url,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "categories": categories,
        "published_at": published_at.isoformat(),
    }

    return ArxivPaper(
        external_id=external_id,
        title=title,
        url=id_url,
        published_at=published_at,
        authors=authors,
        abstract=abstract,
        categories=categories,
        raw_payload=raw_payload,
    )


def fetch_papers(
    since: datetime | None = None,
    overlap_hours: int = 24,
) -> Iterator[ArxivPaper]:
    """Yield ArxivPaper records newest-first, stopping before the watermark.

    ``since`` should always be provided in practice (callers with an empty
    database should pass ``datetime.now(timezone.utc)`` rather than ``None``)
    so the cutoff bounds how far back we page. If ``since`` is genuinely
    ``None``, ``_MAX_PAGES`` still caps worst-case runtime.
    """
    cutoff: datetime | None = None
    if since is not None:
        cutoff = since.astimezone(timezone.utc) - timedelta(hours=overlap_hours)

    start = 0
    for page_num in range(_MAX_PAGES):
        params = urllib.parse.urlencode({
            "search_query": _CATEGORIES,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "start": start,
            "max_results": _PAGE_SIZE,
        })
        url = f"{_BASE_URL}?{params}"
        log.info("fetching arXiv page", extra={"start": start})

        req = urllib.request.Request(url, headers={"User-Agent": "etl-llm-feed/1.0"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            xml_bytes = resp.read()

        root = ET.fromstring(xml_bytes)
        entries = root.findall(f"{{{_ATOM_NS}}}entry")

        if not entries:
            break

        yielded = 0
        for entry in entries:
            paper = _parse_entry(entry)
            if paper is None:
                continue
            if cutoff is not None and paper.published_at <= cutoff:
                return
            yield paper
            yielded += 1

        if yielded < _PAGE_SIZE:
            break

        start += _PAGE_SIZE
    else:
        log.warning("fetch_papers hit _MAX_PAGES safety cap", extra={"max_pages": _MAX_PAGES})
