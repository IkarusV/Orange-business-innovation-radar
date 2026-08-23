import argparse
import logging
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import client as classifier_client
from . import storage as classifier_storage
from . import taxonomy as taxonomy_mod
from ..mlfilter import storage as mlfilter_storage
from common.storage import get_connection

MODULE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = MODULE_DIR.parent
TAXONOMY_PATH = MODULE_DIR / "config" / "taxonomy.json"
PROMPT_TEMPLATE_PATH = MODULE_DIR / "config" / "prompt_template.txt"
DB_PATH = REPO_ROOT / "data" / "articles.db"
LOG_PATH = REPO_ROOT / "logs" / "opportunity_classifier.log"

MAX_WORKERS = 10  # measured safe ceiling with reasoning=none (12+ workers -> majority 429s)
PROGRESS_EVERY = 100


def setup_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
    )
    log = logging.getLogger("opportunity_classifier")
    log.setLevel(logging.INFO)
    return log


def load_unclassified(conn: sqlite3.Connection, limit=None):
    """Pool articles not yet classified, minus anything the ML noise filter
    recommends deleting. An article with no ml_noise_scores row (never
    scored - e.g. RSS, which the filter doesn't cover, or brand new rows
    scored between pipeline stages) is kept by default: an absent score is
    never treated as a delete signal.
    """
    already = classifier_storage.already_classified_ids(conn)
    rows = conn.execute(
        """
        SELECT a.id, a.vertical, a.source_name, a.title, a.summary
        FROM articles a
        JOIN classification_pool p ON p.article_id = a.id
        LEFT JOIN ml_noise_scores n ON n.article_id = a.id
        WHERE n.article_id IS NULL OR n.keep_recommended = 1
        ORDER BY a.id
        """
    ).fetchall()
    todo = [r for r in rows if r[0] not in already]
    if limit:
        todo = todo[:limit]
    return todo


def classify_one(navy_client, template, taxonomy_text, use_case_ids, technology_ids, row, client_context):
    article_id, vertical, source_name, title, summary = row
    result = classifier_client.classify(
        navy_client, template, taxonomy_text, use_case_ids, technology_ids,
        vertical, source_name, title, summary, client_context,
    )
    return article_id, result


def run(limit=None, client_context_path=None) -> None:
    log = setup_logging()

    api_key = os.environ.get("NAVY_API_KEY")
    base_url = os.environ.get("NAVY_BASE_URL", "https://api.navy/v1")
    if not api_key:
        raise RuntimeError("NAVY_API_KEY not set in environment")

    client_context = None
    client_context_ref = None
    if client_context_path:
        p = Path(client_context_path)
        client_context = p.read_text(encoding="utf-8")
        client_context_ref = p.name

    taxonomy = taxonomy_mod.load_taxonomy(TAXONOMY_PATH)
    taxonomy_text = taxonomy_mod.taxonomy_block(taxonomy)
    use_case_ids, technology_ids = taxonomy_mod.valid_ids(taxonomy)
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")

    navy_client = classifier_client.make_client(api_key, base_url)

    conn = get_connection(DB_PATH)
    classifier_storage.ensure_schema(conn)
    mlfilter_storage.ensure_schema(conn)  # so the ML-filter gate below works even if mlfilter hasn't run yet

    todo = load_unclassified(conn, limit=limit)
    log.info("Starting classification run: %d articles to classify", len(todo))

    done = 0
    status_counts = {}
    total_tokens = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(
                classify_one, navy_client, template, taxonomy_text,
                use_case_ids, technology_ids, row, client_context,
            ): row[0]
            for row in todo
        }
        for future in as_completed(futures):
            article_id = futures[future]
            try:
                article_id, result = future.result()
                classifier_storage.upsert_classification(conn, article_id, result, client_context_ref)
                status_counts[result.status] = status_counts.get(result.status, 0) + 1
                total_tokens += result.total_tokens
            except Exception as exc:
                log.error("FAIL article_id=%s - %s", article_id, exc)
                status_counts["error"] = status_counts.get("error", 0) + 1

            done += 1
            if done % PROGRESS_EVERY == 0 or done == len(todo):
                conn.commit()
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed else 0
                remaining = (len(todo) - done) / rate if rate else 0
                log.info(
                    "Progress: %d/%d (%.1f%%) - %s - %.1f/s - ~%.0fs remaining - %d tokens this run",
                    done, len(todo), 100 * done / len(todo), status_counts, rate, remaining, total_tokens,
                )

    conn.commit()
    log.info("Classification done: %s - %d tokens this run", status_counts, total_tokens)

    n_spaces = classifier_storage.recompute_opportunity_spaces(conn)
    log.info("Recomputed %d opportunity spaces", n_spaces)

    print_summary(conn, log)
    conn.close()


def print_summary(conn: sqlite3.Connection, log: logging.Logger) -> None:
    log.info("--- Run summary ---")
    log.info("Opportunity spaces by vertical:")
    for vertical, count in conn.execute(
        "SELECT vertical, COUNT(*) FROM opportunity_spaces GROUP BY vertical ORDER BY 2 DESC"
    ):
        log.info("  %s: %d", vertical, count)

    log.info("Top opportunity spaces by article count:")
    for vertical, uc, tech, count in conn.execute(
        "SELECT vertical, use_case_id, technology_id, article_count FROM opportunity_spaces "
        "ORDER BY article_count DESC LIMIT 15"
    ):
        log.info("  %s | %s | %s: %d articles", vertical, uc, tech, count)

    log.info("Classification status breakdown:")
    for status, count in conn.execute(
        "SELECT status, COUNT(*) FROM article_classifications GROUP BY status ORDER BY 2 DESC"
    ):
        log.info("  %s: %d", status, count)

    total = conn.execute(
        "SELECT SUM(tokens_used), COUNT(*), COUNT(tokens_used) FROM article_classifications"
    ).fetchone()
    sum_tokens, n_rows, n_with_tokens = total
    log.info(
        "Total tokens tracked: %s across %d/%d rows (some early rows predate token tracking)",
        sum_tokens, n_with_tokens, n_rows,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="classify at most N unclassified articles")
    parser.add_argument("--client-context", type=str, default=None, help="path to a client-context file")
    args = parser.parse_args()
    run(limit=args.limit, client_context_path=args.client_context)
