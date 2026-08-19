from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from radar.config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL UNIQUE, domain TEXT, geography TEXT, enabled INTEGER DEFAULT 1, last_status TEXT, last_checked_at TEXT);
CREATE TABLE IF NOT EXISTS articles (id INTEGER PRIMARY KEY, source_id INTEGER, guid TEXT NOT NULL UNIQUE, title TEXT NOT NULL, url TEXT, published_at TEXT, content TEXT, fetched_at TEXT NOT NULL, processed INTEGER DEFAULT 0, FOREIGN KEY(source_id) REFERENCES sources(id));
CREATE TABLE IF NOT EXISTS opportunities (id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, title TEXT NOT NULL, vertical TEXT, use_case TEXT, technology TEXT, geography TEXT, orange_domain TEXT, persona TEXT, signal_type TEXT, horizon TEXT, why_hot_now TEXT, why_it_matters TEXT, next_action TEXT, attractiveness REAL, right_to_win REAL, confidence INTEGER, status TEXT, score_rationale TEXT, factors_json TEXT, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence (id INTEGER PRIMARY KEY, opportunity_id INTEGER NOT NULL, article_id INTEGER, source_name TEXT, source_url TEXT, source_domain TEXT, published_at TEXT, signal_type TEXT, claim TEXT NOT NULL, quality REAL, FOREIGN KEY(opportunity_id) REFERENCES opportunities(id), UNIQUE(opportunity_id, source_url));
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, status TEXT, fetched_count INTEGER DEFAULT 0, processed_count INTEGER DEFAULT 0, notes TEXT);
CREATE TABLE IF NOT EXISTS run_events (id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, created_at TEXT NOT NULL, stage TEXT NOT NULL, message TEXT NOT NULL, current_value INTEGER, total_value INTEGER, FOREIGN KEY(run_id) REFERENCES runs(id));
CREATE TABLE IF NOT EXISTS analysis_candidates (id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, article_id INTEGER NOT NULL, captured_at TEXT NOT NULL, status TEXT NOT NULL, result_json TEXT, error TEXT, promoted_opportunity_id INTEGER, FOREIGN KEY(run_id) REFERENCES runs(id), FOREIGN KEY(article_id) REFERENCES articles(id), FOREIGN KEY(promoted_opportunity_id) REFERENCES opportunities(id));
CREATE TABLE IF NOT EXISTS company_profiles (id INTEGER PRIMARY KEY CHECK(id=1), name TEXT NOT NULL, geography TEXT, website_url TEXT, strategic_prompt TEXT, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS company_documents (id INTEGER PRIMARY KEY, name TEXT NOT NULL, source_type TEXT NOT NULL, source_url TEXT, extracted_text TEXT NOT NULL, added_at TEXT NOT NULL, UNIQUE(name, source_url));
CREATE TABLE IF NOT EXISTS library_documents (id INTEGER PRIMARY KEY, company_name TEXT NOT NULL, name TEXT NOT NULL, original_name TEXT NOT NULL, raw_path TEXT NOT NULL, processed_path TEXT, source_type TEXT NOT NULL, source_url TEXT, raw_chars INTEGER DEFAULT 0, processed_chars INTEGER DEFAULT 0, status TEXT NOT NULL DEFAULT 'raw', stages_json TEXT NOT NULL DEFAULT '[]', error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(company_name, name));
CREATE TABLE IF NOT EXISTS knowledge_settings (id INTEGER PRIMARY KEY CHECK(id=1), max_process_documents INTEGER NOT NULL DEFAULT 5, max_context_documents INTEGER NOT NULL DEFAULT 5, max_context_chars INTEGER NOT NULL DEFAULT 8000, max_report_documents INTEGER NOT NULL DEFAULT 10, max_report_chars INTEGER NOT NULL DEFAULT 60000, updated_at TEXT NOT NULL);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(path: Path | None = None):
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize(path: Path | None = None) -> None:
    with connect(path) as connection:
        connection.executescript(SCHEMA)
        article_columns = {row[1] for row in connection.execute("PRAGMA table_info(articles)")}
        legacy_without_attempt_tracking = "attempt_count" not in article_columns
        for name, definition in {
            "attempt_count": "INTEGER DEFAULT 0",
            "last_error": "TEXT",
            "last_attempt_at": "TEXT",
        }.items():
            if name not in article_columns:
                connection.execute(f"ALTER TABLE articles ADD COLUMN {name} {definition}")
        if legacy_without_attempt_tracking:
            connection.execute(
                """UPDATE articles SET attempt_count=1,last_error='Legacy interrupted run: previous code did not preserve the exact provider or validation error.',last_attempt_at=?
                WHERE processed=0""",
                (utcnow(),),
            )
        connection.execute(
            "UPDATE runs SET status='interrupted',finished_at=?,notes='Application stopped before the run completed.' WHERE status='running'",
            (utcnow(),),
        )
        library_columns = {row[1] for row in connection.execute("PRAGMA table_info(library_documents)")}
        if "search_text" not in library_columns:
            connection.execute("ALTER TABLE library_documents ADD COLUMN search_text TEXT NOT NULL DEFAULT ''")
        connection.execute(
            """INSERT OR IGNORE INTO knowledge_settings(id,max_process_documents,max_context_documents,max_context_chars,max_report_documents,max_report_chars,updated_at)
            VALUES(1,5,5,8000,10,60000,?)""",
            (utcnow(),),
        )
        connection.execute(
            """INSERT OR IGNORE INTO company_profiles(id,name,geography,website_url,strategic_prompt,updated_at)
            VALUES(1,'Orange Business','Belgium / Europe','https://www.orange-business.com/',
            'Evaluate direct Orange Business opportunities as well as partner-led and ecosystem opportunities. Do not penalize an opportunity only because delivery requires another company.',?)""",
            (utcnow(),),
        )


def sync_sources(source_config: list[dict]) -> None:
    with connect() as connection:
        connection.executemany(
            """INSERT INTO sources(name,url,domain,geography,enabled) VALUES(:name,:url,:domain,:geography,:enabled)
            ON CONFLICT(url) DO UPDATE SET name=excluded.name, domain=excluded.domain, geography=excluded.geography, enabled=excluded.enabled""",
            [{**item, "enabled": int(item.get("enabled", True))} for item in source_config],
        )


def rows(query: str, parameters: tuple = ()) -> list[dict]:
    with connect() as connection:
        return [dict(row) for row in connection.execute(query, parameters).fetchall()]


def upsert_opportunity(item: dict) -> int:
    fields = ["slug","title","vertical","use_case","technology","geography","orange_domain","persona","signal_type","horizon","why_hot_now","why_it_matters","next_action","attractiveness","right_to_win","confidence","status","score_rationale","factors_json","updated_at"]
    payload = {key: item.get(key) for key in fields}
    payload["factors_json"] = json.dumps(payload.get("factors_json") or {}, ensure_ascii=True)
    payload["updated_at"] = utcnow()
    placeholders = ",".join(f":{field}" for field in fields)
    updates = ",".join(f"{field}=excluded.{field}" for field in fields if field != "slug")
    with connect() as connection:
        connection.execute(f"INSERT INTO opportunities({','.join(fields)}) VALUES({placeholders}) ON CONFLICT(slug) DO UPDATE SET {updates}", payload)
        return int(connection.execute("SELECT id FROM opportunities WHERE slug=?", (payload["slug"],)).fetchone()[0])


def add_evidence(opportunity_id: int, evidence: dict) -> None:
    with connect() as connection:
        connection.execute(
            """INSERT OR IGNORE INTO evidence(opportunity_id,article_id,source_name,source_url,source_domain,published_at,signal_type,claim,quality)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (opportunity_id, evidence.get("article_id"), evidence.get("source_name"), evidence.get("source_url"), evidence.get("source_domain"), evidence.get("published_at"), evidence.get("signal_type"), evidence["claim"], evidence.get("quality", 0)),
        )


def active_company() -> dict:
    result = rows("SELECT * FROM company_profiles WHERE id=1")
    return result[0] if result else {}


def save_company(name: str, geography: str, website_url: str, strategic_prompt: str) -> None:
    with connect() as connection:
        connection.execute(
            """INSERT INTO company_profiles(id,name,geography,website_url,strategic_prompt,updated_at)
            VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,geography=excluded.geography,
            website_url=excluded.website_url,strategic_prompt=excluded.strategic_prompt,updated_at=excluded.updated_at""",
            (name, geography, website_url, strategic_prompt, utcnow()),
        )


def knowledge_settings() -> dict:
    return rows("SELECT * FROM knowledge_settings WHERE id=1")[0]


def save_knowledge_settings(max_process_documents: int, max_context_documents: int, max_context_chars: int, max_report_documents: int, max_report_chars: int) -> None:
    with connect() as connection:
        connection.execute(
            """UPDATE knowledge_settings SET max_process_documents=?,max_context_documents=?,max_context_chars=?,max_report_documents=?,max_report_chars=?,updated_at=? WHERE id=1""",
            (max_process_documents, max_context_documents, max_context_chars, max_report_documents, max_report_chars, utcnow()),
        )


def save_company_document(name: str, source_type: str, extracted_text: str, source_url: str = "") -> None:
    with connect() as connection:
        connection.execute(
            """INSERT INTO company_documents(name,source_type,source_url,extracted_text,added_at) VALUES(?,?,?,?,?)
            ON CONFLICT(name,source_url) DO UPDATE SET source_type=excluded.source_type,
            extracted_text=excluded.extracted_text,added_at=excluded.added_at""",
            (name, source_type, source_url, extracted_text, utcnow()),
        )


def add_run_event(run_id: int, stage: str, message: str, current: int | None = None, total: int | None = None) -> None:
    with connect() as connection:
        connection.execute(
            "INSERT INTO run_events(run_id,created_at,stage,message,current_value,total_value) VALUES(?,?,?,?,?,?)",
            (run_id, utcnow(), stage, message, current, total),
        )


def save_analysis_candidate(run_id: int, article_id: int, status: str, result: dict | None = None, error: str = "", opportunity_id: int | None = None) -> int:
    with connect() as connection:
        return int(connection.execute(
            """INSERT INTO analysis_candidates(run_id,article_id,captured_at,status,result_json,error,promoted_opportunity_id)
            VALUES(?,?,?,?,?,?,?)""",
            (run_id, article_id, utcnow(), status, json.dumps(result, ensure_ascii=True) if result is not None else None, error[:2000], opportunity_id),
        ).lastrowid)


def update_analysis_candidate(candidate_id: int, status: str, error: str = "", opportunity_id: int | None = None) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE analysis_candidates SET status=?,error=?,promoted_opportunity_id=? WHERE id=?",
            (status, error[:2000], opportunity_id, candidate_id),
        )
