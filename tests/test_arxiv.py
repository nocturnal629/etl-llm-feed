from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import pytest

from lib.python.sources import arxiv
from tests.conftest import make_entry_xml, make_feed_xml


@pytest.mark.parametrize(
    "id_url,expected",
    [
        ("http://arxiv.org/abs/2401.12345v1", "2401.12345"),
        ("http://arxiv.org/abs/2401.12345v10", "2401.12345"),
        ("http://arxiv.org/abs/2401.12345", "2401.12345"),
        ("http://arxiv.org/abs/2401.12345/", "2401.12345"),
    ],
)
def test_extract_arxiv_id(id_url, expected):
    assert arxiv._extract_arxiv_id(id_url) == expected


def test_parse_entry(sample_entry_xml):
    entry = ET.fromstring(sample_entry_xml)
    paper = arxiv._parse_entry(entry)

    assert paper is not None
    assert paper.external_id == "2401.12345"
    assert paper.title == "A Great Paper About Things"
    assert paper.abstract == "This paper studies things. It is great."
    assert paper.authors == ["Jane Doe", "John Smith"]
    assert paper.categories == ["cs.AI", "cs.LG"]
    assert paper.published_at == datetime(2024, 1, 23, 18, 0, 0, tzinfo=timezone.utc)
    assert paper.raw_payload["id"] == "http://arxiv.org/abs/2401.12345v2"


def test_parse_entry_missing_required_field_returns_none():
    entry = ET.fromstring(
        '<entry xmlns="http://www.w3.org/2005/Atom"><summary>no id or title</summary></entry>'
    )
    assert arxiv._parse_entry(entry) is None


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_fetch_papers_stops_at_cutoff(monkeypatch):
    """Pagination should stop yielding once published_at crosses the watermark cutoff."""
    now = datetime(2024, 1, 25, tzinfo=timezone.utc)
    page = make_feed_xml(
        [
            make_entry_xml("2401.00003", "2024-01-24T23:00:00Z"),
            make_entry_xml("2401.00002", "2024-01-24T00:00:00Z"),  # before cutoff (now - 24h)
            make_entry_xml("2401.00001", "2024-01-01T00:00:00Z"),
        ]
    )

    call_count = {"n": 0}

    def fake_urlopen(req, timeout):
        call_count["n"] += 1
        return _FakeResponse(page)

    monkeypatch.setattr(arxiv.urllib.request, "urlopen", fake_urlopen)

    results = list(arxiv.fetch_papers(since=now, overlap_hours=24))

    assert [p.external_id for p in results] == ["2401.00003"]
    assert call_count["n"] == 1


def test_fetch_papers_paginates_until_short_page(monkeypatch):
    page1 = make_feed_xml([make_entry_xml(f"2401.{i:05d}", "2024-01-24T12:00:00Z") for i in range(arxiv._PAGE_SIZE)])
    page2 = make_feed_xml([make_entry_xml("2401.99999", "2024-01-24T12:00:00Z")])
    pages = [page1, page2]

    def fake_urlopen(req, timeout):
        return _FakeResponse(pages.pop(0))

    monkeypatch.setattr(arxiv.urllib.request, "urlopen", fake_urlopen)

    results = list(arxiv.fetch_papers(since=None))

    assert len(results) == arxiv._PAGE_SIZE + 1
    assert not pages  # both pages consumed, then stopped because 2nd page < PAGE_SIZE


def test_fetch_papers_respects_max_pages_safety_cap(monkeypatch):
    """Even with no cutoff and endless full pages, fetch_papers must not loop forever."""

    def fake_urlopen(req, timeout):
        full_page = make_feed_xml(
            [make_entry_xml(f"2401.{i:05d}", "2024-01-24T12:00:00Z") for i in range(arxiv._PAGE_SIZE)]
        )
        return _FakeResponse(full_page)

    monkeypatch.setattr(arxiv.urllib.request, "urlopen", fake_urlopen)

    results = list(arxiv.fetch_papers(since=None))

    assert len(results) == arxiv._MAX_PAGES * arxiv._PAGE_SIZE
