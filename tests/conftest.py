"""Shared test fixtures: fake DB rows/cursors and sample arXiv XML."""
from __future__ import annotations

import pytest


class FakeResult:
    """Mimics the subset of a psycopg cursor used by the codebase."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


@pytest.fixture
def sample_entry_xml() -> str:
    return """
    <entry xmlns="http://www.w3.org/2005/Atom">
        <id>http://arxiv.org/abs/2401.12345v2</id>
        <updated>2024-01-24T10:00:00Z</updated>
        <published>2024-01-23T18:00:00Z</published>
        <title>
          A Great Paper About Things
        </title>
        <summary>
          This paper studies things.
          It is great.
        </summary>
        <author><name>Jane Doe</name></author>
        <author><name>John Smith</name></author>
        <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
        <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
    </entry>
    """


def make_feed_xml(entries_xml: list[str]) -> bytes:
    joined = "\n".join(entries_xml)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
        {joined}
    </feed>""".encode()


def make_entry_xml(external_id: str, published_at: str) -> str:
    return f"""
    <entry xmlns="http://www.w3.org/2005/Atom">
        <id>http://arxiv.org/abs/{external_id}v1</id>
        <updated>{published_at}</updated>
        <published>{published_at}</published>
        <title>Paper {external_id}</title>
        <summary>Abstract for {external_id}</summary>
        <author><name>Author {external_id}</name></author>
        <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
    </entry>
    """
