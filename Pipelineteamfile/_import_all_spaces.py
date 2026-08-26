"""One-off bootstrap: load ALL 309 opportunity spaces from the Pipeline
Opportunity export directly into this project's team DB, instead of the small
paid sample _import_run.py seeded.

This is a direct import of Project A's already-computed (vertical, use_case,
technology) labels - it does NOT call the real Navy classifier, so it costs
nothing, but it also means every imported article gets a placeholder
classification with no signal_type, no geography and no per-article confidence
(those fields don't exist in the export). Spaces built this way will show
"Global / unspecified" geography and an untyped horizon, and their Evidence
quality component will read as unavailable rather than a fabricated number.

The 21 spaces already seeded by _import_run.py were produced by this project's
own live classifier and carry real signal_type/geography/confidence - this
script never overwrites an article that already has a classification row.

Run from the repo root with the venv python:
    .venv\\Scripts\\python.exe Pipelineteamfile\\_import_all_spaces.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

DB_PATH = HERE / "data" / "articles.db"
EXPORT_DIR = REPO_ROOT / "imports" / "pipeline_opportunity_export"


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def main():
    spaces = json.loads((EXPORT_DIR / "opportunity_spaces.json").read_text(encoding="utf-8"))["opportunity_spaces"]
    articles = json.loads((EXPORT_DIR / "articles.json").read_text(encoding="utf-8"))["articles"]

    from common.models import Article
    from common.storage import get_connection, insert_articles
    from opportunity_classifier.collector.storage import (
        ensure_schema, already_classified_ids, recompute_opportunity_spaces,
    )

    now = datetime.now(timezone.utc)
    to_insert = []
    for art in articles.values():
        extra = None
        if art.get("extra"):
            try:
                extra = json.loads(art["extra"])
            except (json.JSONDecodeError, TypeError):
                extra = {"raw": art["extra"]}
        extra = extra or {}
        extra["imported_from"] = "Pipeline Opportunity export (full)"
        extra["source_article_id"] = art["id"]
        to_insert.append(Article(
            vertical=art["vertical"],
            source_name=art["source_name"],
            source_type=art["source_type"],
            title=art["title"],
            url=art.get("url"),
            guid=art.get("guid"),
            published_date=_parse_dt(art.get("published_date")),
            summary=art.get("summary"),
            collected_at=_parse_dt(art.get("collected_at")) or now,
            confidence=art.get("confidence"),
            extra=extra,
            time_window=art.get("time_window"),
        ))

    conn = get_connection(DB_PATH)
    ensure_schema(conn)
    newly_inserted = insert_articles(conn, to_insert)

    # Map export article id -> local articles.id via URL (every export record
    # carries one; url is UNIQUE in the schema so this is a safe join key).
    url_by_source_id = {art["id"]: art["url"] for art in articles.values() if art.get("url")}
    local_id_by_url = {row[0]: row[1] for row in conn.execute("SELECT url, id FROM articles WHERE url IS NOT NULL")}
    local_id_by_source_id = {
        source_id: local_id_by_url[url]
        for source_id, url in url_by_source_id.items()
        if url in local_id_by_url
    }

    already = already_classified_ids(conn)
    classified_at = now.isoformat()
    placeholder_rows = []
    skipped_existing = 0
    unmatched = 0
    for space in spaces:
        for source_aid in space["linked_article_ids"]:
            local_id = local_id_by_source_id.get(source_aid)
            if local_id is None:
                unmatched += 1
                continue
            if local_id in already:
                skipped_existing += 1
                continue
            placeholder_rows.append((
                local_id, space["use_case_id"], space["technology_id"],
                None, None, "classified", None, None, "Pipeline Opportunity export (full import)",
                0, classified_at,
                None, None, None, None, None, None, None,
                None, None, None, None, None, None,
            ))

    conn.executemany(
        """
        INSERT OR IGNORE INTO article_classifications
            (article_id, use_case_id, technology_id, confidence, evidence, status,
             client_relevance, client_relevance_reason, client_context_ref, tokens_used, classified_at,
             signal_type, signal_type_confidence, signal_date, event_date, event_date_precision,
             signal_type_rationale, signal_type_assigned_by,
             countries, regions, region_override, geography_confidence,
             geography_assigned_by, unresolved_countries)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        placeholder_rows,
    )
    conn.commit()

    space_count = recompute_opportunity_spaces(conn)
    total_articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    total_classified = conn.execute("SELECT COUNT(*) FROM article_classifications").fetchone()[0]
    conn.close()

    print(f"export spaces               : {len(spaces)}")
    print(f"newly inserted articles     : {newly_inserted}")
    print(f"articles in team DB (total) : {total_articles}")
    print(f"placeholder rows written    : {len(placeholder_rows)}")
    print(f"skipped (already classified): {skipped_existing}")
    print(f"unmatched linked article ids: {unmatched}")
    print(f"classified rows (total)     : {total_classified}")
    print(f"OPPORTUNITY SPACES (total)  : {space_count}")


if __name__ == "__main__":
    main()
