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
CREATE TABLE IF NOT EXISTS taxonomy_terms (taxonomy_type TEXT NOT NULL, canonical_id TEXT NOT NULL, display_name TEXT NOT NULL, parent_id TEXT, description TEXT, status TEXT NOT NULL, research_origin TEXT NOT NULL, PRIMARY KEY(taxonomy_type,canonical_id));
CREATE TABLE IF NOT EXISTS taxonomy_aliases (taxonomy_type TEXT NOT NULL, canonical_id TEXT NOT NULL, alias TEXT NOT NULL, status TEXT NOT NULL, research_origin TEXT NOT NULL, PRIMARY KEY(taxonomy_type,alias));
CREATE TABLE IF NOT EXISTS intelligence_sources (name TEXT PRIMARY KEY, feed_url TEXT, source_category TEXT, quality_default INTEGER, independence_group TEXT, domain TEXT, vertical_scope TEXT, expected_signal_types TEXT, language TEXT, active INTEGER, research_origin TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS triage_records (id INTEGER PRIMARY KEY, article_guid TEXT NOT NULL, article_link TEXT, title TEXT, source TEXT, classification TEXT NOT NULL, triage_confidence TEXT, signal_type TEXT, vertical_id TEXT, use_case_id TEXT, technology_id TEXT, rationale TEXT, named_organizations TEXT, actor_role TEXT, prompt_version TEXT, model TEXT, classification_method TEXT NOT NULL, research_origin TEXT NOT NULL, review_status TEXT NOT NULL, processed_at TEXT, UNIQUE(article_guid,classification_method,prompt_version));
CREATE TABLE IF NOT EXISTS coverage_gaps (vertical_id TEXT NOT NULL, signal_type TEXT NOT NULL, available_sources INTEGER, independence_groups INTEGER, raw_articles INTEGER, status TEXT, gap TEXT, next_action TEXT, last_reviewed TEXT, research_origin TEXT NOT NULL, PRIMARY KEY(vertical_id,signal_type));
CREATE TABLE IF NOT EXISTS web_search_settings (id INTEGER PRIMARY KEY CHECK(id=1), provider TEXT NOT NULL DEFAULT 'searxng_local', tavily_depth TEXT NOT NULL DEFAULT 'basic', searxng_url TEXT NOT NULL DEFAULT 'http://100.70.65.86:8888', public_searxng_url TEXT NOT NULL DEFAULT '', max_queries INTEGER NOT NULL DEFAULT 3, max_results_per_query INTEGER NOT NULL DEFAULT 5, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS web_search_runs (id INTEGER PRIMARY KEY, purpose TEXT NOT NULL, provider TEXT NOT NULL, opportunity_id INTEGER, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, query_count INTEGER DEFAULT 0, result_count INTEGER DEFAULT 0, error TEXT);
CREATE TABLE IF NOT EXISTS web_search_results (id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, query TEXT NOT NULL, provider TEXT NOT NULL, engine TEXT, rank INTEGER, title TEXT, url TEXT NOT NULL, published_at TEXT, retrieved_at TEXT NOT NULL, content TEXT, provider_score REAL, article_id INTEGER, FOREIGN KEY(run_id) REFERENCES web_search_runs(id), FOREIGN KEY(article_id) REFERENCES articles(id), UNIQUE(run_id,query,url));
CREATE TABLE IF NOT EXISTS opportunity_reports (id INTEGER PRIMARY KEY, opportunity_id INTEGER NOT NULL, company_name TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, model TEXT, search_provider TEXT, search_run_id INTEGER, query_count INTEGER, source_count INTEGER, report_json TEXT, error TEXT, FOREIGN KEY(opportunity_id) REFERENCES opportunities(id), FOREIGN KEY(search_run_id) REFERENCES web_search_runs(id));
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
        evidence_columns = {row[1] for row in connection.execute("PRAGMA table_info(evidence)")}
        for name, definition in {
            "source_category": "TEXT",
            "independence_group": "TEXT",
            "research_origin": "TEXT DEFAULT 'radar_pipeline'",
            "review_status": "TEXT DEFAULT 'pending_review'",
        }.items():
            if name not in evidence_columns:
                connection.execute(f"ALTER TABLE evidence ADD COLUMN {name} {definition}")
        search_columns = {row[1] for row in connection.execute("PRAGMA table_info(web_search_settings)")}
        if "public_searxng_url" not in search_columns:
            connection.execute("ALTER TABLE web_search_settings ADD COLUMN public_searxng_url TEXT NOT NULL DEFAULT ''")
        connection.execute("UPDATE web_search_settings SET provider='searxng_local' WHERE provider='searxng'")
        result_columns = {row[1] for row in connection.execute("PRAGMA table_info(web_search_results)")}
        for name, definition in {
            "content_status": "TEXT NOT NULL DEFAULT 'snippet'",
            "content_source": "TEXT NOT NULL DEFAULT 'search_snippet'",
            "extraction_error": "TEXT",
        }.items():
            if name not in result_columns:
                connection.execute(f"ALTER TABLE web_search_results ADD COLUMN {name} {definition}")
        report_columns = {row[1] for row in connection.execute("PRAGMA table_info(opportunity_reports)")}
        if "search_run_id" not in report_columns:
            connection.execute("ALTER TABLE opportunity_reports ADD COLUMN search_run_id INTEGER")
        connection.execute(
            """UPDATE opportunity_reports SET search_run_id=(
                SELECT r.id FROM web_search_runs r
                WHERE r.purpose='opportunity_report' AND r.opportunity_id=opportunity_reports.opportunity_id
                  AND r.started_at<=opportunity_reports.created_at
                ORDER BY r.started_at DESC LIMIT 1
            ) WHERE search_run_id IS NULL"""
        )
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
        connection.execute(
            """INSERT OR IGNORE INTO web_search_settings(id,provider,tavily_depth,searxng_url,public_searxng_url,max_queries,max_results_per_query,updated_at)
            VALUES(1,'searxng_local','basic','http://100.70.65.86:8888','',3,5,?)""",
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
            """INSERT OR IGNORE INTO evidence(opportunity_id,article_id,source_name,source_url,source_domain,published_at,signal_type,claim,quality,source_category,independence_group,research_origin,review_status)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (opportunity_id, evidence.get("article_id"), evidence.get("source_name"), evidence.get("source_url"), evidence.get("source_domain"), evidence.get("published_at"), evidence.get("signal_type"), evidence["claim"], evidence.get("quality", 0), evidence.get("source_category"), evidence.get("independence_group"), evidence.get("research_origin", "radar_pipeline"), evidence.get("review_status", "pending_review")),
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


def web_search_settings() -> dict:
    return rows("SELECT * FROM web_search_settings WHERE id=1")[0]


def save_web_search_settings(provider: str, tavily_depth: str, searxng_url: str, public_searxng_url: str, max_queries: int, max_results_per_query: int) -> None:
    with connect() as connection:
        connection.execute(
            """UPDATE web_search_settings SET provider=?,tavily_depth=?,searxng_url=?,public_searxng_url=?,max_queries=?,max_results_per_query=?,updated_at=? WHERE id=1""",
            (provider, tavily_depth, searxng_url.rstrip("/"), public_searxng_url.rstrip("/"), max_queries, max_results_per_query, utcnow()),
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
