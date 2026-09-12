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
  "topics": ["llms", "alignment"],
  "key_contribution": "Introduces a new technique.",
  "methodology": "Fine-tunes a base model.",
  "novelty_score": 4
}
"""

INVALID_EXTRACTION_JSON = """
{
  "topics": ["llms"],
  "key_contribution": "Introduces a new technique.",
  "methodology": "Fine-tunes a base model.",
  "novelty_score": 99
}
"""


def test_call_structured_succeeds_first_try():
    client = FakeClient([SimpleNamespace(text=VALID_EXTRACTION_JSON)])
    result = llm._call_structured(client, "gemini-2.0-flash", "prompt", ItemExtraction)

    assert isinstance(result, ItemExtraction)
    assert result.novelty_score == 4
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
    result = llm.extract_item("Some Title", "Some abstract")
    assert result is None


def test_extract_item_returns_parsed_result_on_success(monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda: FakeClient([SimpleNamespace(text=VALID_EXTRACTION_JSON)]))
    result = llm.extract_item("Some Title", "Some abstract")
    assert isinstance(result, ItemExtraction)
    assert result.topics == ["llms", "alignment"]


VALID_DIGEST_JSON = """
{
  "themes": ["alignment", "efficiency"],
  "top_papers": [{"title": "Paper A", "reason": "Very novel."}],
  "executive_summary": "A productive day of research."
}
"""


def test_generate_digest_returns_parsed_result_on_success(monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda: FakeClient([SimpleNamespace(text=VALID_DIGEST_JSON)]))
    result = llm.generate_digest(
        [{"external_id": "2401.00001", "title": "Paper A", "extracted": {"key_contribution": "x", "topics": ["a"]}}]
    )
    assert isinstance(result, DigestSummary)
    assert result.themes == ["alignment", "efficiency"]


def test_generate_digest_returns_none_on_repeated_failure(monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda: FakeClient(
        [SimpleNamespace(text="not json"), SimpleNamespace(text="still not json")]
    ))
    result = llm.generate_digest([{"external_id": "2401.00001", "title": "Paper A", "extracted": {}}])
    assert result is None
