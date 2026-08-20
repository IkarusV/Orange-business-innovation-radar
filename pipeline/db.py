import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "radar.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_quality INTEGER NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    url_canonical TEXT,
    guid TEXT,
    published_at TEXT,
    collected_at TEXT NOT NULL,
    content TEXT,
    geography TEXT,
    vertical_hint TEXT,
    domain_hint TEXT,
    signal_type_hint TEXT,
    extra_json TEXT,
    UNIQUE (guid),
    UNIQUE (url_canonical)
);

CREATE INDEX IF NOT EXISTS idx_signals_coverage
    ON raw_signals (vertical_hint, domain_hint);

CREATE VIEW IF NOT EXISTS coverage_stats AS
    SELECT vertical_hint, domain_hint, COUNT(*) AS signal_count,
           MAX(published_at) AS latest_signal
    FROM raw_signals
    GROUP BY vertical_hint, domain_hint;
"""


def connect(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def insert_signals(conn, signals):
    inserted = 0
    for s in signals:
        try:
            conn.execute(
                """INSERT INTO raw_signals
                   (connector, source_name, source_type, source_quality,
                    title, url, url_canonical, guid, published_at,
                    collected_at, content, geography, vertical_hint,
                    domain_hint, signal_type_hint, extra_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    s["connector"], s["source_name"], s["source_type"],
                    s["source_quality"], s["title"], s.get("url"),
                    s.get("url_canonical"), s.get("guid"),
                    s.get("published_at"),
                    datetime.now(timezone.utc).isoformat(),
                    s.get("content"), s.get("geography"),
                    s.get("vertical_hint"), s.get("domain_hint"),
                    s.get("signal_type_hint"),
                    json.dumps(s.get("extra", {}), ensure_ascii=False),
                ),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            continue
    conn.commit()
    return inserted


def coverage(conn):
    return conn.execute(
        "SELECT * FROM coverage_stats ORDER BY signal_count ASC"
    ).fetchall()


def underrepresented_cells(conn, verticals, domains, threshold):
    counts = {
        (r["vertical_hint"], r["domain_hint"]): r["signal_count"]
        for r in coverage(conn)
    }
    return [
        (v, d) for v in verticals for d in domains
        if counts.get((v, d), 0) < threshold
    ]
