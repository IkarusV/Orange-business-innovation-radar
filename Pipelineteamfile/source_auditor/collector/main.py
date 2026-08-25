"""Classifies every source_name that appears in a completed opportunity space
(a classified article with both use_case_id and technology_id set) into one
fixed publisher-type category (see common/trust.py), which mechanically
determines its trust score. Sources with a category already - including the
5 hardcoded institutional feeds seeded by common.storage - are skipped, so
re-running this never re-audits an already-scored source.

Run from repo root: python -m source_auditor.collector.main [--limit N]
"""
import argparse
import json
import logging
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import client as auditor_client
from common.audit_source import record_audit
from common.storage import get_connection
from common.trust import CATEGORIES, compute_trust

MODULE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = MODULE_DIR.parent
PROMPT_TEMPLATE_PATH = MODULE_DIR / "config" / "audit_prompt_template.txt"
DB_PATH = REPO_ROOT / "data" / "articles.db"
LOG_PATH = REPO_ROOT / "logs" / "source_auditor.log"

MAX_WORKERS = 10  # same measured-safe ceiling as opportunity_classifier
AUDITOR_LABEL = "navy_agent"


def setup_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
    )
    log = logging.getLogger("source_auditor")
    log.setLevel(logging.INFO)
    return log


def load_candidates(conn: sqlite3.Connection, limit=None) -> list:
    """One row per uncategorized source_name that appears in a completed
    opportunity space, with its source_type and a few example titles for
    prompt context.
    """
    rows = conn.execute(
        """
        SELECT DISTINCT a.source_name, a.source_type
        FROM article_classifications ac
        JOIN articles a ON a.id = ac.article_id
        LEFT JOIN sources s ON s.source_name = a.source_name
        WHERE ac.status = 'classified' AND ac.use_case_id IS NOT NULL
          AND ac.technology_id IS NOT NULL AND s.category IS NULL
        ORDER BY a.source_name
        """
    ).fetchall()
    if limit:
        rows = rows[:limit]

    candidates = []
    for source_name, source_type in rows:
        titles = [
            r[0] for r in conn.execute(
                "SELECT title FROM articles WHERE source_name = ? AND title IS NOT NULL LIMIT 5",
                (source_name,),
            )
        ]
        candidates.append({"source_name": source_name, "source_type": source_type, "example_titles": titles})
    return candidates


def audit_one(navy_client, template, categories_block, candidate):
    result = auditor_client.audit(
        navy_client, template, categories_block,
        candidate["source_name"], candidate["source_type"], candidate["example_titles"],
    )
    return candidate["source_name"], result


def run(limit=None) -> dict:
    log = setup_logging()

    api_key = os.environ.get("NAVY_API_KEY")
    base_url = os.environ.get("NAVY_BASE_URL", "https://api.navy/v1")
    if not api_key:
        raise RuntimeError("NAVY_API_KEY not set in environment")

    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    categories_block = auditor_client.build_categories_block(CATEGORIES)
    navy_client = auditor_client.make_client(api_key, base_url)

    conn = get_connection(DB_PATH)
    conn.row_factory = sqlite3.Row
    candidates = load_candidates(conn, limit=limit)
    log.info("Starting source audit run: %d sources to categorize", len(candidates))

    status_counts = {}
    category_counts = {}
    total_tokens = 0
    errors = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(audit_one, navy_client, template, categories_block, c): c["source_name"]
            for c in candidates
        }
        for future in as_completed(futures):
            source_name = futures[future]
            try:
                source_name, result = future.result()
                notes = json.dumps({"evidence": result.evidence, "confidence": result.confidence})
                record_audit(conn, source_name, result.category, AUDITOR_LABEL, notes)
                total_tokens += result.total_tokens
                category_counts[result.category] = category_counts.get(result.category, 0) + 1
                row = conn.execute("SELECT * FROM sources WHERE source_name = ?", (source_name,)).fetchone()
                status = compute_trust(row).status
                status_counts[status] = status_counts.get(status, 0) + 1
                if result.error:
                    log.warning("PARSE_ERROR [%s] - %s", source_name, result.error)
            except Exception as exc:
                errors += 1
                log.error("FAIL [%s] - %s", source_name, exc)

    conn.close()
    elapsed = time.time() - t0
    log.info("Audit run complete: statuses=%s categories=%s - %d tokens - %d errors - %.1fs",
              status_counts, category_counts, total_tokens, errors, elapsed)

    return {
        "audited": len(candidates),
        "status_counts": status_counts,
        "category_counts": category_counts,
        "total_tokens": total_tokens,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 1),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="categorize at most N unaudited sources")
    args = parser.parse_args()
    summary = run(limit=args.limit)
    print(json.dumps(summary, indent=2))
