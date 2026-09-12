from __future__ import annotations

import json
from datetime import date

import pytest

from api.cron import summarize
from lib.python.schemas import DigestSummary, DigestTopPaper
from tests.conftest import FakeResult


class FakeSummarizeConn:
    def __init__(self, item_rows):
        self.item_rows = item_rows
        self.digests: dict[date, dict] = {}

    def execute(self, sql, params=None):
        norm = " ".join(sql.split())

        if norm.startswith("SELECT external_id, title, extracted"):
            return FakeResult(self.item_rows)

        if norm.startswith("INSERT INTO digests"):
            digest_date, item_count, markdown, summary_json, model = params
            self.digests[digest_date] = {
                "item_count": item_count,
                "summary_markdown": markdown,
                "summary_json": summary_json,
                "model": model,
            }
            return FakeResult([])

        raise AssertionError(f"Unexpected SQL in FakeSummarizeConn: {norm}")

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


SAMPLE_DIGEST = DigestSummary(
    themes=["alignment", "efficiency"],
    top_papers=[DigestTopPaper(title="Paper A", reason="Very novel.")],
    executive_summary="A productive day of research.",
)


def test_render_markdown_includes_key_sections():
    md = summarize._render_markdown(SAMPLE_DIGEST, date(2024, 1, 24), 5)
    assert "AI/ML Research Digest — 2024-01-24" in md
    assert "**5 papers** reviewed." in md
    assert "A productive day of research." in md
    assert "- alignment" in md
    assert "### Paper A" in md
    assert "**Why:** Very novel." in md


def test_summarize_skips_when_no_extracted_items(monkeypatch):
    conn = FakeSummarizeConn(item_rows=[])
    monkeypatch.setattr(summarize, "get_conn", lambda: conn)
    monkeypatch.setattr(summarize, "generate_digest", lambda items: pytest.fail("should not be called"))

    result = summarize._summarize(target_date=date(2024, 1, 24))

    assert result == {"ok": True, "skipped": True, "reason": "no items with extraction"}
    assert conn.digests == {}


def test_summarize_returns_error_when_llm_fails(monkeypatch):
    rows = [{"external_id": "2401.00001", "title": "Paper A", "extracted": {"topics": []}}]
    conn = FakeSummarizeConn(item_rows=rows)
    monkeypatch.setattr(summarize, "get_conn", lambda: conn)
    monkeypatch.setattr(summarize, "generate_digest", lambda items: None)

    result = summarize._summarize(target_date=date(2024, 1, 24))

    assert result["ok"] is False
    assert conn.digests == {}


def test_summarize_writes_digest(monkeypatch):
    rows = [{"external_id": "2401.00001", "title": "Paper A", "extracted": {"topics": ["llms"]}}]
    conn = FakeSummarizeConn(item_rows=rows)
    monkeypatch.setattr(summarize, "get_conn", lambda: conn)
    monkeypatch.setattr(summarize, "generate_digest", lambda items: SAMPLE_DIGEST)

    result = summarize._summarize(target_date=date(2024, 1, 24))

    assert result["ok"] is True
    assert result["items"] == 1
    stored = conn.digests[date(2024, 1, 24)]
    assert stored["item_count"] == 1
    assert json.loads(stored["summary_json"])["themes"] == ["alignment", "efficiency"]


def test_summarize_is_idempotent_upsert_on_same_date(monkeypatch):
    """Re-running for the same digest_date must overwrite, not duplicate."""
    rows = [{"external_id": "2401.00001", "title": "Paper A", "extracted": {"topics": ["llms"]}}]
    conn = FakeSummarizeConn(item_rows=rows)
    monkeypatch.setattr(summarize, "get_conn", lambda: conn)
    monkeypatch.setattr(summarize, "generate_digest", lambda items: SAMPLE_DIGEST)

    summarize._summarize(target_date=date(2024, 1, 24))
    summarize._summarize(target_date=date(2024, 1, 24))

    assert len(conn.digests) == 1
    assert conn.digests[date(2024, 1, 24)]["item_count"] == 1
