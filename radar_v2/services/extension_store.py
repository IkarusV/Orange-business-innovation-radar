from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from radar_v2.constants import DOCUMENTS, EXTENSION_DB


SCHEMA = """
CREATE TABLE IF NOT EXISTS company_profiles (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, geography TEXT, website TEXT, focus TEXT, active INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, name TEXT NOT NULL, path TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL, size_bytes INTEGER NOT NULL, updated_at TEXT NOT NULL, FOREIGN KEY(company_id) REFERENCES company_profiles(id));
CREATE TABLE IF NOT EXISTS custom_sources (id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL UNIQUE, category TEXT, active INTEGER NOT NULL DEFAULT 1, added_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS search_runs (id INTEGER PRIMARY KEY, query TEXT NOT NULL, provider TEXT NOT NULL, created_at TEXT NOT NULL, result_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY, opportunity_id INTEGER NOT NULL, title TEXT NOT NULL, company TEXT NOT NULL, source_count INTEGER NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pipeline_runs (id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, stage TEXT, progress INTEGER NOT NULL DEFAULT 0, message TEXT, summary_json TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS app_settings (id INTEGER PRIMARY KEY CHECK(id=1), ai_base_url TEXT NOT NULL, ai_model TEXT NOT NULL, ai_mode TEXT NOT NULL, search_provider TEXT NOT NULL, searxng_url TEXT NOT NULL, tavily_depth TEXT NOT NULL, max_search_results INTEGER NOT NULL, max_research_queries INTEGER NOT NULL DEFAULT 5, updated_at TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    EXTENSION_DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(EXTENSION_DB)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(SCHEMA)
    connection.execute(
        """INSERT OR IGNORE INTO company_profiles(name,geography,website,focus,active,updated_at)
        VALUES('Orange Business','Belgium & Europe','https://www.orange-business.com','Trusted digital services, secure connectivity, cloud, data and AI',1,?)""",
        (now(),),
    )
    connection.execute(
        """INSERT OR IGNORE INTO app_settings(id,ai_base_url,ai_model,ai_mode,search_provider,searxng_url,tavily_depth,max_search_results,updated_at)
        VALUES(1,'https://api.navy/v1','gpt-5.6-luna','responses','searxng','http://localhost:8888','basic',8,?)""",
        (now(),),
    )
    document_columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)")}
    for name, definition in {
        "processed_path": "TEXT",
        "selected": "INTEGER NOT NULL DEFAULT 0",
        "processing_note": "TEXT",
        "context_enabled": "INTEGER NOT NULL DEFAULT 0",
        "context_scope": "TEXT NOT NULL DEFAULT 'Everywhere'",
    }.items():
        if name not in document_columns:
            connection.execute(f"ALTER TABLE documents ADD COLUMN {name} {definition}")
    settings_columns = {row[1] for row in connection.execute("PRAGMA table_info(app_settings)")}
    if "max_research_queries" not in settings_columns:
        connection.execute("ALTER TABLE app_settings ADD COLUMN max_research_queries INTEGER NOT NULL DEFAULT 5")
    connection.execute("UPDATE documents SET context_scope='Everywhere' WHERE context_scope='everywhere'")
    connection.execute("UPDATE documents SET context_scope='Opportunity mapping' WHERE context_scope='opportunity_mapping'")
    connection.execute("UPDATE documents SET context_scope='Scoring & fit' WHERE context_scope='scoring_fit'")
    connection.execute("UPDATE documents SET context_scope='Business reports' WHERE context_scope='business_reports'")
    connection.commit()
    return connection


def _rows(query: str, params: tuple = ()) -> list[dict]:
    with connect() as connection:
        return [dict(row) for row in connection.execute(query, params)]


def companies() -> list[dict]:
    return _rows("SELECT * FROM company_profiles ORDER BY active DESC,name")


def active_company() -> dict:
    return _rows("SELECT * FROM company_profiles ORDER BY active DESC LIMIT 1")[0]


def save_company(name: str, geography: str, website: str, focus: str) -> None:
    with connect() as connection:
        connection.execute("UPDATE company_profiles SET active=0")
        connection.execute(
            """INSERT INTO company_profiles(name,geography,website,focus,active,updated_at) VALUES(?,?,?,?,1,?)
            ON CONFLICT(name) DO UPDATE SET geography=excluded.geography,website=excluded.website,focus=excluded.focus,active=1,updated_at=excluded.updated_at""",
            (name.strip(), geography.strip(), website.strip(), focus.strip(), now()),
        )
        connection.commit()
    (DOCUMENTS / safe_name(name)).mkdir(parents=True, exist_ok=True)


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._") or "company"


def save_document(filename: str, content: bytes) -> dict:
    company = active_company()
    folder = DOCUMENTS / safe_name(company["name"])
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / safe_name(filename)
    stem, suffix = target.stem, target.suffix
    index = 2
    while target.exists():
        target = folder / f"{stem}_{index}{suffix}"
        index += 1
    target.write_bytes(content)
    with connect() as connection:
        document_id = connection.execute(
            "INSERT INTO documents(company_id,name,path,kind,status,size_bytes,updated_at) VALUES(?,?,?,?,?,?,?)",
            (company["id"], target.name, str(target), suffix.lstrip(".").upper() or "FILE", "Ready", len(content), now()),
        ).lastrowid
        connection.commit()
    return {"id": document_id, "name": target.name}


def documents() -> list[dict]:
    result = _rows("""SELECT d.id,c.name company,d.name,d.kind,d.status,d.size_bytes,d.updated_at,d.selected,d.processed_path,d.context_enabled,d.context_scope
        FROM documents d JOIN company_profiles c ON c.id=d.company_id ORDER BY d.updated_at DESC""")
    for item in result:
        size = item.pop("size_bytes")
        item["size"] = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024*1024):.1f} MB"
        item["updated"] = item.pop("updated_at")[:10]
        item["selected"] = bool(item["selected"])
        item["context_enabled"] = bool(item["context_enabled"])
        item["processed_name"] = Path(item["processed_path"]).name if item.get("processed_path") else ""
    return result


def selected_document_texts(max_documents: int, max_chars: int, scopes: tuple[str, ...] = ("Opportunity mapping", "Scoring & fit", "Everywhere")) -> list[dict]:
    """Return bounded plain-text company references for the team classifier context."""
    result = []
    used = 0
    placeholders = ",".join("?" for _ in scopes)
    for item in _rows(f"SELECT name,path,processed_path,kind,context_scope FROM documents WHERE status='Processed' AND context_enabled=1 AND context_scope IN ({placeholders}) ORDER BY updated_at DESC", scopes):
        if len(result) >= max_documents or used >= max_chars:
            break
        path = Path(item["processed_path"] or item["path"])
        if path.suffix.lower() not in {".txt", ".md", ".csv", ".json", ".html", ".htm"} or not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        remaining = max_chars - used
        result.append({"name": item["name"], "scope": item["context_scope"], "text": text[:remaining]})
        used += min(len(text), remaining)
    return result


def business_report_context(max_documents: int = 5, max_chars: int = 16000) -> list[dict]:
    return selected_document_texts(max_documents, max_chars, ("Business reports", "Everywhere"))


def add_source(name: str, url: str, category: str) -> None:
    with connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO custom_sources(name,url,category,added_at) VALUES(?,?,?,?)",
            (name.strip(), url.strip(), category.strip(), now()),
        )
        connection.commit()


def custom_sources() -> list[dict]:
    return _rows("SELECT * FROM custom_sources ORDER BY added_at DESC")


def fetch_custom_source_articles() -> list[dict]:
    """Fetch one readable evidence record per active priority URL."""
    output = []
    for source in _rows("SELECT * FROM custom_sources WHERE active=1 ORDER BY added_at DESC"):
        try:
            response = requests.get(source["url"], headers={"User-Agent": "Innovation-Radar-V2/1.0"}, timeout=25)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup.find_all(("script", "style", "nav", "footer", "header", "form", "noscript")):
                tag.decompose()
            container = soup.find("article") or soup.find("main") or soup.body or soup
            text = " ".join(container.get_text(" ", strip=True).split())[:8000]
            title = soup.title.get_text(" ", strip=True) if soup.title else source["name"]
            if len(text) >= 120:
                output.append({"title": title, "url": source["url"], "source": source["name"], "date": "Recent", "excerpt": text})
        except requests.RequestException:
            continue
    return output


def save_search(query: str, provider: str, results: list[dict]) -> int:
    with connect() as connection:
        search_id = connection.execute(
            "INSERT INTO search_runs(query,provider,created_at,result_json) VALUES(?,?,?,?)",
            (query, provider, now(), json.dumps(results, ensure_ascii=False)),
        ).lastrowid
        connection.commit()
    return search_id


def latest_search() -> dict | None:
    result = _rows("SELECT * FROM search_runs ORDER BY id DESC LIMIT 1")
    if not result:
        return None
    item = result[0]
    item["results"] = json.loads(item.pop("result_json"))
    return item


def reports() -> list[dict]:
    return _rows("SELECT id,title,company,source_count sources,created_at created,status FROM reports ORDER BY id DESC")


def save_focused_report(opportunity_id: int, title: str, payload: dict, source_count: int) -> int:
    company = active_company()
    with connect() as connection:
        report_id = connection.execute(
            "INSERT INTO reports(opportunity_id,title,company,source_count,created_at,status,payload_json) VALUES(?,?,?,?,?,?,?)",
            (opportunity_id, title, company["name"], source_count, now(), "Ready", json.dumps(payload, ensure_ascii=False)),
        ).lastrowid
        connection.commit()
    return int(report_id)


def focused_report(report_id: int) -> dict | None:
    result = _rows("SELECT * FROM reports WHERE id=?", (report_id,))
    if not result:
        return None
    item = result[0]
    item["payload"] = json.loads(item.pop("payload_json"))
    return item


def settings() -> dict:
    return _rows("SELECT * FROM app_settings WHERE id=1")[0]


def save_settings(ai_base_url: str, ai_model: str, ai_mode: str, search_provider: str, searxng_url: str, tavily_depth: str, max_search_results: int, max_research_queries: int = 5) -> None:
    with connect() as connection:
        connection.execute(
            """UPDATE app_settings SET ai_base_url=?,ai_model=?,ai_mode=?,search_provider=?,searxng_url=?,tavily_depth=?,max_search_results=?,max_research_queries=?,updated_at=? WHERE id=1""",
            (ai_base_url.rstrip("/"), ai_model.strip(), ai_mode, search_provider, searxng_url.rstrip("/"), tavily_depth, max_search_results, max(1, min(20, int(max_research_queries))), now()),
        )
        connection.commit()


def toggle_document(document_id: int) -> None:
    with connect() as connection:
        connection.execute("UPDATE documents SET selected=CASE selected WHEN 1 THEN 0 ELSE 1 END,updated_at=? WHERE id=?", (now(), document_id))
        connection.commit()


def toggle_document_context(document_id: int) -> None:
    with connect() as connection:
        connection.execute("UPDATE documents SET context_enabled=CASE context_enabled WHEN 1 THEN 0 ELSE 1 END,updated_at=? WHERE id=? AND status='Processed'", (now(), document_id))
        connection.commit()


def set_document_scope(document_id: int, scope: str) -> None:
    allowed = {"Opportunity mapping", "Scoring & fit", "Business reports", "Everywhere"}
    if scope not in allowed:
        raise ValueError("Unsupported company context destination")
    with connect() as connection:
        connection.execute("UPDATE documents SET context_scope=?,updated_at=? WHERE id=?", (scope, now(), document_id))
        connection.commit()


def selected_documents() -> list[dict]:
    return _rows("SELECT * FROM documents WHERE selected=1 ORDER BY updated_at DESC")


def update_document_processing(document_id: int, status: str, processed_path: str = "", note: str = "") -> None:
    with connect() as connection:
        if status == "Processed":
            connection.execute("UPDATE documents SET status=?,processed_path=?,processing_note=?,context_enabled=1,context_scope='Everywhere',updated_at=? WHERE id=?", (status, processed_path or None, note, now(), document_id))
        else:
            connection.execute("UPDATE documents SET status=?,processed_path=?,processing_note=?,updated_at=? WHERE id=?", (status, processed_path or None, note, now(), document_id))
        connection.commit()


def save_company_report(title: str, path: Path, source_count: int) -> int:
    company = active_company()
    size = path.stat().st_size
    with connect() as connection:
        document_id = connection.execute(
            "INSERT INTO documents(company_id,name,path,kind,status,size_bytes,updated_at,processed_path,selected) VALUES(?,?,?,?,?,?,?,?,0)",
            (company["id"], path.name, str(path), "REPORT", "Processed", size, now(), str(path)),
        ).lastrowid
        connection.execute(
            "INSERT INTO reports(opportunity_id,title,company,source_count,created_at,status,payload_json) VALUES(0,?,?,?,?,?,?)",
            (title, company["name"], source_count, now(), "Ready", json.dumps({"path": str(path)})),
        )
        connection.commit()
    return document_id
