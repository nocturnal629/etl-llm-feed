"""Serverless-safe Postgres connection helper.

Opens a fresh connection per call and closes it when the context exits.
No long-lived pool — safe for short-lived function invocations.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

import psycopg
from psycopg.rows import dict_row

from .config import config


@contextmanager
def get_conn() -> Generator[psycopg.Connection, None, None]:
    with psycopg.connect(config.database_url, row_factory=dict_row) as conn:
        yield conn
