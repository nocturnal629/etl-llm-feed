"""Gemini client wrappers for structured LLM outputs."""
from __future__ import annotations

from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from .config import config
from .logging import get_logger
from .schemas import DigestSummary, ItemExtraction

log = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

_FLASH_MODEL = "gemini-2.0-flash"
_PRO_MODEL = "gemini-2.5-pro"


def _client() -> genai.Client:
    return genai.Client(api_key=config.gemini_api_key)


def _call_structured(
    client: genai.Client,
    model: str,
    prompt: str,
    schema: type[T],
) -> T:
    """Call Gemini with structured JSON output. Retries once on validation failure."""
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
    )
    last_error = ""
    for attempt in range(2):
        contents = (
            prompt
            if attempt == 0
            else f"{prompt}\n\nYour previous response failed schema validation: {last_error}\nPlease fix and try again."
        )
        response = client.models.generate_content(model=model, contents=contents, config=cfg)
        try:
            return schema.model_validate_json(response.text)
        except ValidationError as exc:
            last_error = str(exc)
            if attempt == 1:
                raise
    raise RuntimeError("unreachable")


def extract_item(title: str, abstract: str) -> ItemExtraction | None:
    """Per-record extraction with Gemini Flash. Returns None on failure (don't block ingestion)."""
    client = _client()
    prompt = (
        "Extract structured metadata from this AI/ML research paper.\n\n"
        f"Title: {title}\n\nAbstract: {abstract}"
    )
    try:
        return _call_structured(client, _FLASH_MODEL, prompt, ItemExtraction)
    except Exception as exc:
        log.error("item extraction failed", extra={"title": title[:80], "error": str(exc)})
        return None


def generate_digest(items: list[dict]) -> DigestSummary | None:
    """Daily digest generation with Gemini Pro. Returns None on failure."""
    client = _client()
    papers_text = "\n\n".join(
        "ID: {ext}\nTitle: {title}\nKey contribution: {contrib}\nTopics: {topics}".format(
            ext=item["external_id"],
            title=item["title"],
            contrib=(item.get("extracted") or {}).get("key_contribution", "N/A"),
            topics=", ".join((item.get("extracted") or {}).get("topics", [])),
        )
        for item in items
    )
    prompt = (
        "You are an AI research editor. Analyze today's arXiv papers and produce a structured digest.\n\n"
        f"Papers:\n{papers_text}\n\n"
        "Identify 3-5 major themes across these papers, pick the top 3 papers worth reading "
        "with a one-sentence reason each, and write a one-paragraph executive summary."
    )
    try:
        return _call_structured(client, _PRO_MODEL, prompt, DigestSummary)
    except Exception as exc:
        log.error("digest generation failed", extra={"item_count": len(items), "error": str(exc)})
        return None
