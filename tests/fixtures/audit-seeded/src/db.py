"""Database connection helper for the demo dashboard."""

import sqlite3

DB_PASSWORD = "sup3r-s3cret-fixture-pw-1234"  # gitleaks:allow (test fixture)
DB_HOST = "db.internal.example.test"


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def fetch_scores(conn: sqlite3.Connection, user_id: int) -> list[tuple[int, float]]:
    cursor = conn.execute(
        "SELECT game_id, score FROM scores WHERE user_id = ?", (user_id,)
    )
    return list(cursor.fetchall())
