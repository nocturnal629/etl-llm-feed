from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from lib.python.schemas import ArxivPaper, DigestSummary, DigestTopPaper, ItemExtraction


def test_arxiv_paper_valid():
    paper = ArxivPaper(
        external_id="2401.12345",
        title="A Paper",
        url="http://arxiv.org/abs/2401.12345",
        published_at=datetime.now(timezone.utc),
        authors=["Jane Doe"],
        abstract="An abstract.",
        categories=["cs.AI"],
        raw_payload={"id": "http://arxiv.org/abs/2401.12345"},
    )
    assert paper.external_id == "2401.12345"


def test_arxiv_paper_missing_required_field():
    with pytest.raises(ValidationError):
        ArxivPaper(
            title="A Paper",
            url="http://arxiv.org/abs/2401.12345",
            published_at=datetime.now(timezone.utc),
            authors=[],
            abstract="",
            categories=[],
            raw_payload={},
        )


@pytest.mark.parametrize("novelty_score", [1, 3, 5])
def test_item_extraction_valid_novelty_scores(novelty_score):
    item = ItemExtraction(
        topics=["llms"],
        key_contribution="Does a thing.",
        methodology="Uses a method.",
        novelty_score=novelty_score,
    )
    assert item.novelty_score == novelty_score


@pytest.mark.parametrize("novelty_score", [0, 6, -1])
def test_item_extraction_rejects_out_of_range_novelty_score(novelty_score):
    with pytest.raises(ValidationError):
        ItemExtraction(
            topics=["llms"],
            key_contribution="Does a thing.",
            methodology="Uses a method.",
            novelty_score=novelty_score,
        )


def test_digest_summary_nested_top_papers():
    digest = DigestSummary(
        themes=["theme a", "theme b"],
        top_papers=[DigestTopPaper(title="Paper A", reason="Very novel.")],
        executive_summary="A summary of the day.",
    )
    assert digest.top_papers[0].title == "Paper A"


def test_digest_summary_rejects_wrong_type_for_themes():
    with pytest.raises(ValidationError):
        DigestSummary(
            themes="not a list",
            top_papers=[],
            executive_summary="A summary.",
        )
