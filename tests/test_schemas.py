from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from lib.python.schemas import DigestSummary, DigestTopItem, ItemExtraction, WikiChange


def test_wiki_change_valid():
    change = WikiChange(
        external_id="123",
        title="Diamond Sword",
        url="https://minecraft.wiki/w/Diamond_Sword",
        published_at=datetime.now(timezone.utc),
        change_type="edit",
        user="Steve",
        body_text="The Diamond Sword is a weapon.",
        raw_payload={"rcid": 123},
    )
    assert change.external_id == "123"
    assert change.comment == ""


def test_wiki_change_missing_required_field():
    with pytest.raises(ValidationError):
        WikiChange(
            title="Diamond Sword",
            url="https://minecraft.wiki/w/Diamond_Sword",
            published_at=datetime.now(timezone.utc),
            change_type="edit",
            user="Steve",
            raw_payload={},
        )


@pytest.mark.parametrize("interest_score", [1, 3, 5])
def test_item_extraction_valid_interest_scores(interest_score):
    item = ItemExtraction(
        topics=["redstone"],
        summary="Documents a compact redstone farm.",
        interest_score=interest_score,
    )
    assert item.interest_score == interest_score


@pytest.mark.parametrize("interest_score", [0, 6, -1])
def test_item_extraction_rejects_out_of_range_interest_score(interest_score):
    with pytest.raises(ValidationError):
        ItemExtraction(
            topics=["redstone"],
            summary="Documents a compact redstone farm.",
            interest_score=interest_score,
        )


def test_digest_summary_nested_top_items():
    digest = DigestSummary(
        themes=["theme a", "theme b"],
        top_items=[DigestTopItem(title="Diamond Sword", reason="Major rebalance this week.")],
        executive_summary="A summary of the day.",
    )
    assert digest.top_items[0].title == "Diamond Sword"


def test_digest_summary_rejects_wrong_type_for_themes():
    with pytest.raises(ValidationError):
        DigestSummary(
            themes="not a list",
            top_items=[],
            executive_summary="A summary.",
        )
