import json
import sqlite3
from pathlib import Path
from typing import List

from .models import Article

BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT UNIQUE,
    guid TEXT,
    published_date TEXT,
    summary TEXT,
    collected_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_articles_vertical ON articles(vertical);
CREATE INDEX IF NOT EXISTS idx_articles_source_type ON articles(source_type);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(BASE_SCHEMA)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
    if "confidence" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN confidence TEXT")
    if "extra" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN extra TEXT")
    if "time_window" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN time_window TEXT")
    # guid dedup as a second, independent unique key alongside url (RSS relies on
    # url, TED has no single canonical url and relies on guid=publication-number)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_guid_unique "
        "ON articles(guid) WHERE guid IS NOT NULL"
    )
    conn.commit()


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    _ensure_schema(conn)
    return conn


def insert_articles(conn: sqlite3.Connection, articles: List[Article]) -> int:
    """Insert articles, skipping ones already seen (by URL or GUID). Returns new-row count."""
    inserted = 0
    for article in articles:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO articles
                (vertical, source_name, source_type, title, url, guid, published_date,
                 summary, collected_at, confidence, extra, time_window)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article.vertical,
                article.source_name,
                article.source_type,
                article.title,
                article.url,
                article.guid,
                article.published_date.isoformat() if article.published_date else None,
                article.summary,
                article.collected_at.isoformat(),
                article.confidence,
                json.dumps(article.extra) if article.extra is not None else None,
                article.time_window,
            ),
        )
        if cursor.rowcount:
            inserted += 1
    conn.commit()
    return inserted
