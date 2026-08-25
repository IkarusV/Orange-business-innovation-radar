import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .models import Article
from .trust import HARDCODED_SOURCES

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

# Category-anchored source trust: one publisher-type category per source_name
# (independent of which collector observed it). category NULL means
# "unaudited". Score/status are never stored - always recomputed from the
# category via common.trust's anchor table, so retuning an anchor never
# requires re-auditing every source.
SOURCES_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    source_name TEXT PRIMARY KEY,
    category TEXT,
    audited_at TEXT,
    auditor TEXT,
    notes TEXT
);
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
    conn.executescript(SOURCES_SCHEMA)
    conn.commit()


def ensure_sources_seeded(conn: sqlite3.Connection) -> int:
    """Insert a row (as unaudited) for every source_name in `articles` not yet in
    `sources`. Idempotent - safe to call on every connect. Returns rows added.
    """
    cursor = conn.execute(
        "INSERT OR IGNORE INTO sources (source_name) "
        "SELECT DISTINCT source_name FROM articles"
    )
    conn.commit()
    return cursor.rowcount


def seed_hardcoded_sources(conn: sqlite3.Connection) -> None:
    """This pipeline's own primary institutional feeds are trusted outright,
    never sent through the category auditor. Idempotent - deterministic values,
    safe to re-upsert on every connect.
    """
    audited_at = datetime.now(timezone.utc).isoformat()
    for source_name, category in HARDCODED_SOURCES.items():
        conn.execute(
            """
            INSERT INTO sources (source_name, category, audited_at, auditor, notes)
            VALUES (?, ?, ?, 'hardcoded', 'Primary institutional data feed - trusted outright, not auditable as a news publisher')
            ON CONFLICT(source_name) DO UPDATE SET
                category=excluded.category, audited_at=excluded.audited_at,
                auditor=excluded.auditor, notes=excluded.notes
            """,
            (source_name, category, audited_at),
        )
    conn.commit()


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    _ensure_schema(conn)
    ensure_sources_seeded(conn)
    seed_hardcoded_sources(conn)
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
