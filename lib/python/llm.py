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


def extract_item(title: str, body_text: str) -> ItemExtraction | None:
    """Per-record extraction with Gemini Flash. Returns None on failure (don't block ingestion)."""
    client = _client()
    prompt = (
        "Extract structured metadata from this Minecraft Wiki page.\n\n"
        f"Title: {title}\n\n"
        f"Current article intro: {body_text or '(no extract available)'}"
    )
    try:
        return _call_structured(client, _FLASH_MODEL, prompt, ItemExtraction)
    except Exception as exc:
        log.error("item extraction failed", extra={"title": title[:80], "error": str(exc)})
        return None


def generate_digest(items: list[dict]) -> DigestSummary | None:
    """Daily digest generation with Gemini Pro. Returns None on failure."""
    client = _client()
    items_text = "\n\n".join(
        "ID: {ext}\nTitle: {title}\nSummary: {summary}\nTopics: {topics}".format(
            ext=item["external_id"],
            title=item["title"],
            summary=(item.get("extracted") or {}).get("summary", "N/A"),
            topics=", ".join((item.get("extracted") or {}).get("topics", [])),
        )
        for item in items
    )
    prompt = (
        "You are an editor tracking updates to the Minecraft Wiki. Analyze today's page "
        "changes and produce a structured digest.\n\n"
        f"Changes:\n{items_text}\n\n"
        "Identify 3-5 major themes or trends across these changes, pick the top 3 items worth "
        "checking out with a one-sentence reason each, and write a one-paragraph executive "
        "summary of today's wiki activity."
    )
    try:
        return _call_structured(client, _PRO_MODEL, prompt, DigestSummary)
    except Exception as exc:
        log.error("digest generation failed", extra={"item_count": len(items), "error": str(exc)})
        return None
