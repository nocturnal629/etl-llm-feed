from __future__ import annotations

import json
from datetime import datetime, timezone

from lib.python.sources import minecraft_wiki as wiki


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def make_rc_entry(rcid: int, title: str, timestamp: str, **overrides) -> dict:
    base = {
        "type": "edit",
        "ns": 0,
        "title": title,
        "pageid": 1000 + rcid,
        "rcid": rcid,
        "timestamp": timestamp,
        "user": "SomeEditor",
        "comment": "Updated info",
    }
    base.update(overrides)
    return base


def make_rc_response(entries: list[dict], cont: dict | None = None) -> dict:
    resp: dict = {"query": {"recentchanges": entries}}
    if cont:
        resp["continue"] = cont
    return resp


def make_extracts_response(titles_to_extract: dict[str, str]) -> dict:
    pages = {str(i): {"pageid": i, "title": title, "extract": extract} for i, (title, extract) in enumerate(titles_to_extract.items())}
    return {"query": {"pages": pages}}


def _dispatch(rc_responses: list[dict], extracts_response_fn=None):
    rc_responses = list(rc_responses)

    def fake_urlopen(req, timeout):
        url = req.full_url
        if "list=recentchanges" in url:
            return _FakeResponse(rc_responses.pop(0))
        if "prop=extracts" in url:
            extracts_fn = extracts_response_fn or (lambda url: make_extracts_response({}))
            return _FakeResponse(extracts_fn(url))
        raise AssertionError(f"Unexpected request URL: {url}")

    return fake_urlopen


def test_parse_change_builds_wiki_change():
    entry = make_rc_entry(1, "Diamond Sword", "2024-01-24T18:00:00Z", type="edit", user="Steve", comment="Added trivia")
    extracts = {"Diamond Sword": "The Diamond Sword is a weapon in Minecraft."}

    change = wiki._parse_change(entry, extracts)

    assert change is not None
    assert change.external_id == "1"
    assert change.title == "Diamond Sword"
    assert change.url == "https://minecraft.wiki/w/Diamond_Sword"
    assert change.published_at == datetime(2024, 1, 24, 18, 0, 0, tzinfo=timezone.utc)
    assert change.change_type == "edit"
    assert change.user == "Steve"
    assert change.comment == "Added trivia"
    assert change.body_text == "The Diamond Sword is a weapon in Minecraft."
    assert change.raw_payload == entry


def test_parse_change_missing_required_field_returns_none():
    assert wiki._parse_change({"title": "No id or timestamp"}, {}) is None


def test_parse_change_defaults_when_optional_fields_missing():
    entry = {"rcid": 2, "title": "Some Page", "timestamp": "2024-01-24T18:00:00Z"}
    change = wiki._parse_change(entry, {})

    assert change is not None
    assert change.user == "unknown"
    assert change.comment == ""
    assert change.body_text == ""
    assert change.change_type == "edit"


def test_fetch_extracts_batches_and_dedupes(monkeypatch):
    calls = []

    def extracts_fn(url):
        calls.append(url)
        return make_extracts_response({"Page A": "Extract A", "Page B": "Extract B"})

    monkeypatch.setattr(wiki.urllib.request, "urlopen", _dispatch([], extracts_fn))

    result = wiki._fetch_extracts(["Page A", "Page B", "Page A"])

    assert result == {"Page A": "Extract A", "Page B": "Extract B"}
    assert len(calls) == 1  # deduped titles fit in a single batch


def test_fetch_changes_stops_at_cutoff(monkeypatch):
    now = datetime(2024, 1, 25, tzinfo=timezone.utc)
    rc_response = make_rc_response(
        [
            make_rc_entry(3, "Page C", "2024-01-24T23:00:00Z"),
            make_rc_entry(2, "Page B", "2024-01-24T00:00:00Z"),  # before cutoff (now - 24h)
            make_rc_entry(1, "Page A", "2024-01-01T00:00:00Z"),
        ]
    )
    monkeypatch.setattr(wiki.urllib.request, "urlopen", _dispatch([rc_response]))

    results = list(wiki.fetch_changes(since=now, overlap_hours=24))

    assert [c.external_id for c in results] == ["3"]


def test_fetch_changes_paginates_via_continue_token(monkeypatch):
    page1 = make_rc_response(
        [make_rc_entry(i, f"Page {i}", "2024-01-24T12:00:00Z") for i in range(wiki._PAGE_SIZE)],
        cont={"rccontinue": "20240124120000|99", "continue": "-||"},
    )
    page2 = make_rc_response([make_rc_entry(999, "Last Page", "2024-01-24T12:00:00Z")])
    rc_urls = []

    def fake_urlopen(req, timeout):
        url = req.full_url
        if "list=recentchanges" in url:
            rc_urls.append(url)
            return _FakeResponse(page1 if len(rc_urls) == 1 else page2)
        return _FakeResponse(make_extracts_response({}))

    monkeypatch.setattr(wiki.urllib.request, "urlopen", fake_urlopen)

    results = list(wiki.fetch_changes(since=None))

    assert len(results) == wiki._PAGE_SIZE + 1
    assert len(rc_urls) == 2
    assert "rccontinue=20240124120000" in rc_urls[1]


def test_fetch_changes_respects_max_pages_safety_cap(monkeypatch):
    def fake_urlopen(req, timeout):
        url = req.full_url
        if "list=recentchanges" in url:
            full_page = make_rc_response(
                [make_rc_entry(i, f"Page {i}", "2024-01-24T12:00:00Z") for i in range(wiki._PAGE_SIZE)],
                cont={"rccontinue": "more", "continue": "-||"},
            )
            return _FakeResponse(full_page)
        return _FakeResponse(make_extracts_response({}))

    monkeypatch.setattr(wiki.urllib.request, "urlopen", fake_urlopen)

    results = list(wiki.fetch_changes(since=None))

    assert len(results) == wiki._MAX_PAGES * wiki._PAGE_SIZE
