"""Pydantic models for source records and LLM-structured outputs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WikiChange(BaseModel):
    external_id: str
    title: str
    url: str
    published_at: datetime
    change_type: str  # "new" or "edit", as reported by the MediaWiki API
    user: str
    comment: str = ""
    body_text: str = ""
    raw_payload: dict[str, Any]


class ItemExtraction(BaseModel):
    topics: list[str] = Field(description="2-4 word tags, e.g. 'redstone', 'mob', 'crafting' (1 to 6 items)")
    summary: str = Field(description="One sentence describing what this page/edit is about")
    interest_score: int = Field(
        ge=1, le=5, description="How significant this change is, 1 (minor/cosmetic) to 5 (major new content)"
    )


class DigestTopItem(BaseModel):
    title: str
    reason: str = Field(description="One sentence on why this item stood out today")


class DigestSummary(BaseModel):
    themes: list[str] = Field(description="3 to 5 major themes/trends from the day's changes")
    top_items: list[DigestTopItem] = Field(description="Top 3 items worth checking out")
    executive_summary: str = Field(description="One paragraph executive summary of the day's activity")
