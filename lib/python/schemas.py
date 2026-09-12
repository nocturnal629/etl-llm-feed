"""Pydantic models for source records and LLM-structured outputs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ArxivPaper(BaseModel):
    external_id: str
    title: str
    url: str
    published_at: datetime
    authors: list[str]
    abstract: str
    categories: list[str]
    raw_payload: dict[str, Any]


class ItemExtraction(BaseModel):
    topics: list[str] = Field(description="2-5 word topic tags (1 to 8 items)")
    key_contribution: str = Field(description="One sentence describing the main contribution")
    methodology: str = Field(description="One sentence describing the approach or methods used")
    novelty_score: int = Field(ge=1, le=5, description="Novelty on a scale of 1 (incremental) to 5 (breakthrough)")


class DigestTopPaper(BaseModel):
    title: str
    reason: str = Field(description="One sentence on why this paper is worth reading today")


class DigestSummary(BaseModel):
    themes: list[str] = Field(description="3 to 5 major themes from the day's papers")
    top_papers: list[DigestTopPaper] = Field(description="Top 3 papers worth reading")
    executive_summary: str = Field(description="One paragraph executive summary of the day's research")
