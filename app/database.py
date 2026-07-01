"""
database.py

SQLite persistence layer for review history.
All raw SQL and connection handling lives here — no other module should
touch sqlite3 directly. This keeps the storage mechanism swappable later
(e.g. to Postgres) without touching main.py or the frontend.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "reviews.db"


def get_connection() -> sqlite3.Connection:
    """
    Open a new SQLite connection.

    A fresh connection per call is used rather than a pooled/shared one —
    SQLite connections are not safe to share across threads, and FastAPI
    can serve requests on different threads. Each call is cheap enough
    that this is not a performance concern at this scale.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets us access columns by name
    return conn


def init_db() -> None:
    """
    Create the reviews table if it does not already exist.

    Called once at FastAPI startup via the lifespan context manager in
    main.py. Safe to call multiple times — CREATE TABLE IF NOT EXISTS
    is idempotent.
    """
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pr_url TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                issue_count INTEGER NOT NULL,
                critical_count INTEGER NOT NULL,
                warning_count INTEGER NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def save_review(
    pr_url: str,
    issue_count: int,
    critical_count: int,
    warning_count: int,
) -> None:
    """
    Persist a single completed review to the database.

    Args:
        pr_url: The GitHub PR URL that was reviewed.
        issue_count: Total number of issues found (all severities).
        critical_count: Number of issues with severity == "critical".
        warning_count: Number of issues with severity == "warning".

    Timestamp is generated here (UTC, ISO 8601) rather than passed in,
    so callers don't need to worry about timezone consistency.
    """
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO reviews (pr_url, timestamp, issue_count, critical_count, warning_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                pr_url,
                datetime.now(timezone.utc).isoformat(),
                issue_count,
                critical_count,
                warning_count,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_reviews(limit: int = 10) -> list[dict[str, Any]]:
    """
    Fetch the most recent reviews, newest first.

    Args:
        limit: Maximum number of reviews to return. Defaults to 10 to
            match the Streamlit sidebar's display requirement.

    Returns:
        A list of dicts, each representing one row. Using dicts (not
        sqlite3.Row objects) here so the FastAPI route can pass this
        straight into a Pydantic response model without extra conversion.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT id, pr_url, timestamp, issue_count, critical_count, warning_count
            FROM reviews
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()