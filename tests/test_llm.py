from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from lib.python import llm
from lib.python.schemas import DigestSummary, ItemExtraction


class FakeModels:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.models = FakeModels(responses)


VALID_EXTRACTION_JSON = """
{
  "topics": ["redstone", "farm"],
  "summary": "Documents a compact automatic sugarcane farm.",
  "interest_score": 4
}
"""

INVALID_EXTRACTION_JSON = """
{
  "topics": ["redstone"],
  "summary": "Documents a compact automatic sugarcane farm.",
  "interest_score": 99
}
"""


def test_call_structured_succeeds_first_try():
    client = FakeClient([SimpleNamespace(text=VALID_EXTRACTION_JSON)])
    result = llm._call_structured(client, "gemini-2.0-flash", "prompt", ItemExtraction)

    assert isinstance(result, ItemExtraction)
    assert result.interest_score == 4
    assert len(client.models.calls) == 1


def test_call_structured_retries_once_then_succeeds():
    client = FakeClient(
        [
            SimpleNamespace(text=INVALID_EXTRACTION_JSON),
            SimpleNamespace(text=VALID_EXTRACTION_JSON),
        ]
    )
    result = llm._call_structured(client, "gemini-2.0-flash", "original prompt", ItemExtraction)

    assert isinstance(result, ItemExtraction)
    assert len(client.models.calls) == 2
    retry_contents = client.models.calls[1]["contents"]
    assert "original prompt" in retry_contents
    assert "failed schema validation" in retry_contents


def test_call_structured_raises_after_two_failures():
    client = FakeClient(
        [
            SimpleNamespace(text=INVALID_EXTRACTION_JSON),
            SimpleNamespace(text=INVALID_EXTRACTION_JSON),
        ]
    )
    with pytest.raises(ValidationError):
        llm._call_structured(client, "gemini-2.0-flash", "prompt", ItemExtraction)
    assert len(client.models.calls) == 2


def test_extract_item_returns_none_on_repeated_failure(monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda: FakeClient(
        [SimpleNamespace(text=INVALID_EXTRACTION_JSON), SimpleNamespace(text=INVALID_EXTRACTION_JSON)]
    ))
    result = llm.extract_item("Diamond Sword", "Some article intro")
    assert result is None


def test_extract_item_returns_parsed_result_on_success(monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda: FakeClient([SimpleNamespace(text=VALID_EXTRACTION_JSON)]))
    result = llm.extract_item("Diamond Sword", "Some article intro")
    assert isinstance(result, ItemExtraction)
    assert result.topics == ["redstone", "farm"]


VALID_DIGEST_JSON = """
{
  "themes": ["redstone", "combat balance"],
  "top_items": [{"title": "Diamond Sword", "reason": "Major rebalance this week."}],
  "executive_summary": "A busy day for the Minecraft Wiki."
}
"""


def test_generate_digest_returns_parsed_result_on_success(monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda: FakeClient([SimpleNamespace(text=VALID_DIGEST_JSON)]))
    result = llm.generate_digest(
        [{"external_id": "123", "title": "Diamond Sword", "extracted": {"summary": "x", "topics": ["a"]}}]
    )
    assert isinstance(result, DigestSummary)
    assert result.themes == ["redstone", "combat balance"]


def test_generate_digest_returns_none_on_repeated_failure(monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda: FakeClient(
        [SimpleNamespace(text="not json"), SimpleNamespace(text="still not json")]
    ))
    result = llm.generate_digest([{"external_id": "123", "title": "Diamond Sword", "extracted": {}}])
    assert result is None
