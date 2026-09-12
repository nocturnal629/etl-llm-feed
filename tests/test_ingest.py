from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from api.cron import ingest
from lib.python.schemas import ItemExtraction, WikiChange
from tests.conftest import FakeResult


class FakeIngestConn:
    """Minimal stand-in for a psycopg connection, backed by an in-memory dict."""

    def __init__(self, watermark=None):
        self.watermark = watermark
        self.items: dict[str, dict] = {}
        self.commits = 0

    def execute(self, sql, params=None):
        norm = " ".join(sql.split())

        if norm.startswith("SELECT MAX(published_at)"):
            return FakeResult([{"watermark": self.watermark}])

        if norm.startswith("SELECT id FROM items WHERE external_id"):
            (external_id,) = params
            row = self.items.get(external_id)
            return FakeResult([{"id": row["id"]}] if row else [])

        if norm.startswith("INSERT INTO items"):
            external_id, title, url, published_at, raw_payload = params
            self.items[external_id] = {
                "id": str(len(self.items) + 1),
                "external_id": external_id,
                "title": title,
                "url": url,
                "published_at": published_at,
                "raw_payload": raw_payload,
                "extracted": None,
            }
            return FakeResult([])

        if norm.startswith("UPDATE items SET extracted"):
            extracted_json, external_id = params
            self.items[external_id]["extracted"] = extracted_json
            return FakeResult([])

        if norm.startswith("UPDATE items SET raw_payload"):
            raw_payload, external_id = params
            self.items[external_id]["raw_payload"] = raw_payload
            return FakeResult([])

        raise AssertionError(f"Unexpected SQL in FakeIngestConn: {norm}")

    def commit(self):
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _change(external_id: str, published_at: datetime) -> WikiChange:
    return WikiChange(
        external_id=external_id,
        title=f"Page {external_id}",
        url=f"https://minecraft.wiki/w/Page_{external_id}",
        published_at=published_at,
        change_type="edit",
        user="Steve",
        body_text="Some article intro.",
        raw_payload={"rcid": external_id},
    )


@pytest.fixture
def patched_extraction(monkeypatch):
    monkeypatch.setattr(
        ingest,
        "extract_item",
        lambda title, body_text: ItemExtraction(topics=["redstone"], summary="x", interest_score=3),
    )


def test_ingest_first_run_with_empty_db_uses_now_as_since(monkeypatch):
    """With no watermark, effective_since must be bounded (not None) to avoid an unbounded backfill."""
    conn = FakeIngestConn(watermark=None)
    monkeypatch.setattr(ingest, "get_conn", lambda: conn)

    captured = {}

    def fake_fetch_changes(since=None, **kwargs):
        captured["since"] = since
        return iter([])

    monkeypatch.setattr(ingest, "fetch_changes", fake_fetch_changes)

    ingest._ingest()

    assert captured["since"] is not None
    assert (datetime.now(timezone.utc) - captured["since"]).total_seconds() < 5


def test_ingest_inserts_new_items_and_runs_extraction(monkeypatch, patched_extraction):
    conn = FakeIngestConn(watermark=None)
    monkeypatch.setattr(ingest, "get_conn", lambda: conn)
    changes = [_change("123", datetime(2024, 1, 24, tzinfo=timezone.utc))]
    monkeypatch.setattr(ingest, "fetch_changes", lambda since=None, **kw: iter(changes))

    result = ingest._ingest()

    assert result["fetched"] == 1
    assert result["inserted"] == 1
    assert result["updated"] == 0
    assert result["extracted"] == 1
    assert conn.items["123"]["extracted"] is not None


def test_ingest_is_idempotent_on_second_run(monkeypatch, patched_extraction):
    """Re-running with the same changes must not create duplicates or re-extract."""
    conn = FakeIngestConn(watermark=None)
    monkeypatch.setattr(ingest, "get_conn", lambda: conn)
    changes = [_change("123", datetime(2024, 1, 24, tzinfo=timezone.utc))]
    monkeypatch.setattr(ingest, "fetch_changes", lambda since=None, **kw: iter(changes))

    first = ingest._ingest()
    assert first["inserted"] == 1
    assert first["extracted"] == 1

    second = ingest._ingest()

    assert second["inserted"] == 0
    assert second["updated"] == 1
    assert second["extracted"] == 0
    assert len(conn.items) == 1


def test_ingest_updates_raw_payload_without_touching_extracted(monkeypatch, patched_extraction):
    conn = FakeIngestConn(watermark=None)
    monkeypatch.setattr(ingest, "get_conn", lambda: conn)
    changes = [_change("123", datetime(2024, 1, 24, tzinfo=timezone.utc))]
    monkeypatch.setattr(ingest, "fetch_changes", lambda since=None, **kw: iter(changes))
    ingest._ingest()

    original_extracted = conn.items["123"]["extracted"]

    updated_change = _change("123", datetime(2024, 1, 24, tzinfo=timezone.utc))
    updated_change.raw_payload["revised"] = True
    monkeypatch.setattr(ingest, "fetch_changes", lambda since=None, **kw: iter([updated_change]))

    ingest._ingest()

    assert json.loads(conn.items["123"]["raw_payload"])["revised"] is True
    assert conn.items["123"]["extracted"] == original_extracted
