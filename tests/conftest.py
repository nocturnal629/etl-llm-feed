"""Shared test fixtures: a fake DB cursor result used by the ingest/summarize tests."""
from __future__ import annotations


class FakeResult:
    """Mimics the subset of a psycopg cursor used by the codebase."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)
