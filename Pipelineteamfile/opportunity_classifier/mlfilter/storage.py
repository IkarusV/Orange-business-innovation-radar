"""Schema and writes for the ML noise filter's own output table.

This module only ever creates and writes ml_noise_scores. Articles are never
physically deleted anywhere in this project — a low score is a recommendation to
skip sending the article to the LLM, never a reason to remove the row.
"""
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS ml_noise_scores (
    article_id INTEGER PRIMARY KEY,
    source_group TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    usefulness_prob REAL NOT NULL,
    keep_recommended INTEGER NOT NULL,
    threshold REAL NOT NULL,
    was_training_row INTEGER NOT NULL,
    scored_at TEXT NOT NULL,
    FOREIGN KEY (article_id) REFERENCES articles(id)
);
CREATE INDEX IF NOT EXISTS idx_ml_noise_group ON ml_noise_scores(source_group);
CREATE INDEX IF NOT EXISTS idx_ml_noise_keep ON ml_noise_scores(keep_recommended);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def labeled_rows(conn: sqlite3.Connection, source_types) -> list:
    placeholders = ",".join("?" for _ in source_types)
    return conn.execute(
        f"""
        SELECT a.id, a.vertical, c.status
        FROM article_classifications c
        JOIN articles a ON a.id = c.article_id
        WHERE a.source_type IN ({placeholders})
        ORDER BY a.id
        """,
        tuple(source_types),
    ).fetchall()


def all_rows(conn: sqlite3.Connection, source_types) -> list:
    placeholders = ",".join("?" for _ in source_types)
    return conn.execute(
        f"SELECT id, vertical FROM articles WHERE source_type IN ({placeholders}) ORDER BY id",
        tuple(source_types),
    ).fetchall()


def write_scores(conn: sqlite3.Connection, group: str, model_name: str, rows, threshold: float) -> int:
    now = datetime.now(timezone.utc).isoformat()
    payload = [
        (
            int(article_id), group, model_name, float(prob),
            int(prob >= threshold), float(threshold),
            int(was_training_row), now,
        )
        for article_id, prob, was_training_row in rows
    ]
    conn.executemany(
        """
        INSERT OR REPLACE INTO ml_noise_scores
            (article_id, source_group, embedding_model, usefulness_prob, keep_recommended,
             threshold, was_training_row, scored_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        payload,
    )
    conn.commit()
    return len(payload)
