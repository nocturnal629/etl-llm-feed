"""Applies all *.sql migration files in this directory, in filename order."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

MIGRATIONS_DIR = Path(__file__).parent


def run() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("ERROR: DATABASE_URL environment variable is not set.")

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        print("No .sql migration files found — nothing to apply.")
        return

    with psycopg.connect(database_url) as conn:
        for path in migration_files:
            print(f"  Applying {path.name} ...", end=" ")
            conn.execute(path.read_text())
            print("done")
        conn.commit()

    print(f"\nAll {len(migration_files)} migration(s) applied successfully.")


if __name__ == "__main__":
    run()
