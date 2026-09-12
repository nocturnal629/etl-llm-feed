"""Single source of truth for all environment-variable configuration.

Values are read lazily on first access so imports don't fail in test contexts,
but a missing value raises loudly the first time it is used.
"""
from __future__ import annotations

import os
from functools import cached_property

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable '{name}' is not set.")
    return value


class _Config:
    @cached_property
    def database_url(self) -> str:
        return _require("DATABASE_URL")

    @cached_property
    def gemini_api_key(self) -> str:
        return _require("GEMINI_API_KEY")


config = _Config()
