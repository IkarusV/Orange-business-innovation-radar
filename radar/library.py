from __future__ import annotations

import json
import re
from pathlib import Path

from radar.ai import AIClient
from radar.company import DocumentError, extract_document
from radar.config import ROOT
from radar.db import connect, knowledge_settings, rows, utcnow

LIBRARY_ROOT = ROOT / "Documents"
STAGES = ("collection", "opportunity_naming", "scoring", "narrative", "all")
SUPPORTED_SUFFIXES = {".pdf", ".pptx", ".docx", ".txt", ".md", ".csv", ".json", ".html", ".htm"}


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._")
    return cleaned or "company"


def company_directory(company_name: str) -> Path:
    path = LIBRARY_ROOT / safe_name(company_name)
    path.mkdir(parents=True, exist_ok=True)
    (path / "processed").mkdir(exist_ok=True)
    return path


def _unique_name(company_name: str, original: str) -> str:
    base = safe_name(Path(original).stem)
    suffix = Path(original).suffix.lower() or ".txt"
    candidate = f"{base}{suffix}"
    existing = {item["name"] for item in rows("SELECT name FROM library_documents WHERE company_name=?", (company_name,))}
    index = 2
    while candidate in existing:
        candidate = f"{base}_{index}{suffix}"
        index += 1
    return candidate


def add_document(company_name: str, original_name: str, data: bytes, content_type: str = "", source_url: str = "") -> dict:
    extracted = extract_document(original_name, data, content_type)
    name = _unique_name(company_name, original_name)
    folder = company_directory(company_name)
    raw_path = folder / name
    raw_path.write_bytes(data)
    now = utcnow()
    with connect() as connection:
        document_id = connection.execute(
            """INSERT INTO library_documents(company_name,name,original_name,raw_path,source_type,source_url,raw_chars,status,created_at,updated_at,search_text)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (company_name, name, original_name, str(raw_path), content_type or raw_path.suffix.lstrip("."), source_url, len(extracted), "raw", now, now, extracted),
        ).lastrowid
    return {"id": document_id, "name": name, "raw_path": str(raw_path), "extracted": extracted}


def refresh_library_index(company_name: str) -> dict:
    folder = company_directory(company_name)
    indexed = {Path(item["raw_path"]).resolve() for item in rows("SELECT raw_path FROM library_documents WHERE company_name=? AND raw_path<>''", (company_name,))}
    added = skipped = 0
    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES or path.resolve() in indexed:
            continue
        try:
            extracted = extract_document(path.name, path.read_bytes(), path.suffix.lstrip("."))
            now = utcnow()
            with connect() as connection:
                connection.execute(
                    """INSERT OR IGNORE INTO library_documents(company_name,name,original_name,raw_path,source_type,raw_chars,status,created_at,updated_at,search_text)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (company_name, path.name, path.name, str(path), path.suffix.lstrip("."), len(extracted), "raw", now, now, extracted),
                )
            added += 1
        except DocumentError:
            skipped += 1
    return {"added": added, "skipped": skipped}


def _document_text(document: dict) -> str:
    path = Path(document["raw_path"])
    if not path.exists():
        raise DocumentError(f"Raw document is missing: {path}")
    return extract_document(document["original_name"], path.read_bytes(), document.get("source_type", ""))


def process_document(document_id: int, client: AIClient, stages: list[str]) -> dict:
    document = rows("SELECT * FROM library_documents WHERE id=?", (document_id,))[0]
    text = _document_text(document)
    prompt = """You are a company knowledge librarian. Summarize ONLY the supplied document. Do not import facts from other documents. Return JSON with: summary, key_facts (array), company_language (array of useful terms), strategic_signals (array), opportunities_or_capabilities (array), risks_or_unknowns (array), and document_type. Keep each item concise and mark uncertainty. This summary will guide another AI but is not authoritative."""
    result = client.generate_json(prompt, f"DOCUMENT NAME: {document['original_name']}\nDOCUMENT TEXT:\n{text[:80000]}")
    summary_text = json.dumps(result, ensure_ascii=False, indent=2)
    processed_path = company_directory(document["company_name"]) / "processed" / f"{Path(document['name']).stem}.processed.txt"
    processed_path.write_text(summary_text, encoding="utf-8")
    with connect() as connection:
        connection.execute(
            "UPDATE library_documents SET processed_path=?,processed_chars=?,status='processed',stages_json=?,error=NULL,updated_at=?,search_text=search_text || ? WHERE id=?",
            (str(processed_path), len(summary_text), json.dumps(sorted(set(stages) & set(STAGES))), utcnow(), "\n" + summary_text, document_id),
        )
    return {"id": document_id, "name": document["name"], "processed_path": str(processed_path), "result": result}


def create_report(company_name: str, document_ids: list[int], client: AIClient) -> dict:
    limits = knowledge_settings()
    documents = [rows("SELECT * FROM library_documents WHERE id=? AND company_name=?", (doc_id, company_name))[0] for doc_id in document_ids[:limits["max_report_documents"]]]
    if not documents:
        raise DocumentError("Select at least one document for a report.")
    combined = "\n\n".join(f"SOURCE DOCUMENT: {doc['original_name']}\n{Path(doc['processed_path']).read_text(encoding='utf-8') if doc.get('processed_path') and Path(doc['processed_path']).exists() else _document_text(doc)}" for doc in documents)
    prompt = """You are a senior company knowledge analyst. Create one combined report from ONLY the supplied document summaries/text. Keep source boundaries clear, identify repeated patterns and contradictions, and separate facts from hypotheses. Return JSON with: report_summary, repeated_themes, company_vocabulary, strategic_priorities, relevant_capabilities, contradictions_or_unknowns, and source_documents. Do not invent facts."""
    result = client.generate_json(prompt, f"COMPANY: {company_name}\n{combined[:limits['max_report_chars']]}")
    report_number = rows("SELECT COUNT(*) count FROM library_documents WHERE company_name=? AND source_type='report'", (company_name,))[0]["count"] + 1
    name = f"report_{safe_name(company_name)}_{report_number}.txt"
    path = company_directory(company_name) / "processed" / name
    text = json.dumps(result, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    now = utcnow()
    with connect() as connection:
        report_id = connection.execute(
            """INSERT INTO library_documents(company_name,name,original_name,raw_path,processed_path,source_type,source_url,raw_chars,processed_chars,status,stages_json,created_at,updated_at,search_text)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (company_name, name, name, "", str(path), "report", f"library://{company_name}/{len(documents)}-documents", 0, len(text), "processed", json.dumps(["all"]), now, now, text),
        ).lastrowid
    return {"id": report_id, "name": name, "result": result}


def set_stages(document_id: int, stages: list[str]) -> None:
    with connect() as connection:
        connection.execute("UPDATE library_documents SET stages_json=?,updated_at=? WHERE id=?", (json.dumps(sorted(set(stages) & set(STAGES))), utcnow(), document_id))


def rename_document(document_id: int, new_name: str) -> dict:
    document = rows("SELECT * FROM library_documents WHERE id=?", (document_id,))[0]
    safe = safe_name(new_name)
    suffix = Path(document["name"]).suffix
    if suffix and not safe.lower().endswith(suffix.lower()) and document["source_type"] != "report":
        safe += suffix
    folder = company_directory(document["company_name"])
    raw_path = Path(document["raw_path"]) if document["raw_path"] else None
    processed_path = Path(document["processed_path"]) if document.get("processed_path") else None
    new_raw = folder / safe if raw_path else None
    new_processed = folder / "processed" / f"{Path(safe).stem}.processed.txt" if processed_path else None
    if (new_raw and new_raw.exists() and new_raw != raw_path) or (new_processed and new_processed.exists() and new_processed != processed_path):
        raise DocumentError(f"A file named {safe} already exists for this company.")
    if raw_path and raw_path.exists():
        raw_path.rename(new_raw)
    if processed_path and processed_path.exists():
        processed_path.rename(new_processed)
    with connect() as connection:
        connection.execute(
            "UPDATE library_documents SET name=?,raw_path=?,processed_path=?,updated_at=? WHERE id=?",
            (safe, str(new_raw) if new_raw else "", str(new_processed) if new_processed else "", utcnow(), document_id),
        )
    return {"id": document_id, "name": safe}


def library_context(company_name: str, stage: str, max_documents: int, max_chars: int, include_all: bool = True) -> str:
    documents = rows("SELECT * FROM library_documents WHERE company_name=? AND status='processed' ORDER BY updated_at DESC", (company_name,))
    selected = []
    for document in documents:
        stages = json.loads(document.get("stages_json") or "[]")
        matches_all = include_all and "all" in stages
        if not matches_all and stage not in stages:
            continue
        if not document.get("processed_path") or not Path(document["processed_path"]).exists():
            continue
        selected.append(document)
        if len(selected) >= max_documents:
            break
    parts = ["ADDITIONAL COMPANY INFORMATION (guidance, not a restriction):"]
    used = 0
    for document in selected:
        text = Path(document["processed_path"]).read_text(encoding="utf-8")
        remaining = max_chars - used
        if remaining <= 0:
            break
        parts.append(f"\nCOMPANY DOCUMENT SUMMARY: {document['name']}\n{text[:remaining]}")
        used += min(len(text), remaining)
    return "\n".join(parts) if selected else ""
