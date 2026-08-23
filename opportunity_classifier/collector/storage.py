import json
import sqlite3
from datetime import datetime
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS article_classifications (
    article_id INTEGER PRIMARY KEY,
    use_case_id TEXT,
    technology_id TEXT,
    confidence REAL,
    evidence TEXT,
    status TEXT NOT NULL,
    client_relevance REAL,
    client_relevance_reason TEXT,
    client_context_ref TEXT,
    tokens_used INTEGER,
    classified_at TEXT NOT NULL,
    FOREIGN KEY (article_id) REFERENCES articles(id)
);
CREATE INDEX IF NOT EXISTS idx_classifications_status ON article_classifications(status);

CREATE TABLE IF NOT EXISTS opportunity_spaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical TEXT NOT NULL,
    use_case_id TEXT NOT NULL,
    technology_id TEXT NOT NULL,
    article_count INTEGER NOT NULL,
    avg_client_relevance REAL,
    linked_article_ids TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    UNIQUE(vertical, use_case_id, technology_id)
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(article_classifications)")}
    if "tokens_used" not in cols:
        conn.execute("ALTER TABLE article_classifications ADD COLUMN tokens_used INTEGER")
    conn.commit()


def already_classified_ids(conn: sqlite3.Connection) -> set:
    return {row[0] for row in conn.execute("SELECT article_id FROM article_classifications")}


def upsert_classification(
    conn: sqlite3.Connection,
    article_id: int,
    result,
    client_context_ref: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO article_classifications
            (article_id, use_case_id, technology_id, confidence, evidence, status,
             client_relevance, client_relevance_reason, client_context_ref, tokens_used, classified_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            article_id,
            result.use_case_id,
            result.technology_id,
            result.confidence,
            result.evidence,
            result.status,
            result.client_relevance,
            result.client_relevance_reason,
            client_context_ref,
            result.total_tokens,
            datetime.utcnow().isoformat(),
        ),
    )


def recompute_opportunity_spaces(conn: sqlite3.Connection) -> int:
    """Recompute all opportunity_spaces from current article_classifications.
    Idempotent: upserts on (vertical, use_case_id, technology_id), preserving
    first_seen_at across reruns.
    """
    rows = conn.execute(
        """
        SELECT a.vertical, c.use_case_id, c.technology_id, c.article_id, c.client_relevance
        FROM article_classifications c
        JOIN articles a ON a.id = c.article_id
        WHERE c.status = 'classified'
          AND c.use_case_id IS NOT NULL
          AND c.technology_id IS NOT NULL
        """
    ).fetchall()

    spaces = {}
    for vertical, use_case_id, technology_id, article_id, client_relevance in rows:
        key = (vertical, use_case_id, technology_id)
        bucket = spaces.setdefault(key, {"article_ids": [], "relevances": []})
        bucket["article_ids"].append(article_id)
        if client_relevance is not None:
            bucket["relevances"].append(client_relevance)

    now = datetime.utcnow().isoformat()
    for (vertical, use_case_id, technology_id), bucket in spaces.items():
        article_ids = sorted(bucket["article_ids"])
        avg_relevance = (
            sum(bucket["relevances"]) / len(bucket["relevances"]) if bucket["relevances"] else None
        )
        conn.execute(
            """
            INSERT INTO opportunity_spaces
                (vertical, use_case_id, technology_id, article_count, avg_client_relevance,
                 linked_article_ids, first_seen_at, last_updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(vertical, use_case_id, technology_id) DO UPDATE SET
                article_count = excluded.article_count,
                avg_client_relevance = excluded.avg_client_relevance,
                linked_article_ids = excluded.linked_article_ids,
                last_updated_at = excluded.last_updated_at
            """,
            (
                vertical, use_case_id, technology_id, len(article_ids), avg_relevance,
                json.dumps(article_ids), now, now,
            ),
        )
    conn.commit()
    return len(spaces)
