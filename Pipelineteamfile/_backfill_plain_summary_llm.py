"""Fill in signal_type_plain_summary for every LLM-classified row that
predates that field, via a small, cheap rewrite call per article - not a full
reclassification (see client.rewrite_plain_summary): input is the existing
signal_type_rationale, output is one plain sentence. use_case_id,
technology_id, confidence and signal_type are all untouched.

Run from the repo root with the venv python:
    .venv\\Scripts\\python.exe Pipelineteamfile\\_backfill_plain_summary_llm.py
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from opportunity_classifier.collector import client as classifier_client
from opportunity_classifier.collector import storage as classifier_storage
from common.storage import get_connection

DB_PATH = HERE / "data" / "articles.db"
MAX_WORKERS = 10
PROGRESS_EVERY = 20


def load_todo(conn):
    return conn.execute(
        """
        SELECT article_id, signal_type_rationale
        FROM article_classifications
        WHERE signal_type_assigned_by = 'llm'
          AND signal_type_plain_summary IS NULL
          AND signal_type_rationale IS NOT NULL
          AND signal_type_rationale != ''
        ORDER BY article_id
        """
    ).fetchall()


def _rewrite_one(navy_client, article_id, rationale):
    tokens = []
    summary = classifier_client.rewrite_plain_summary(navy_client, rationale, tokens)
    return article_id, summary, sum(tokens)


def main():
    api_key = os.environ.get("NAVY_API_KEY")
    base_url = os.environ.get("NAVY_BASE_URL", "https://api.navy/v1")
    if not api_key:
        raise RuntimeError("NAVY_API_KEY not set in environment")
    navy_client = classifier_client.make_client(api_key, base_url)

    conn = get_connection(DB_PATH)
    classifier_storage.ensure_schema(conn)

    todo = load_todo(conn)
    print(f"rows to rewrite: {len(todo)}")

    filled, errors, total_tokens = 0, 0, 0
    done = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(_rewrite_one, navy_client, article_id, rationale): article_id
            for article_id, rationale in todo
        }
        for future in as_completed(futures):
            article_id = futures[future]
            try:
                article_id, summary, tokens = future.result()
                if summary:
                    classifier_storage.update_plain_summary(conn, article_id, summary, tokens=tokens)
                    filled += 1
                    total_tokens += tokens
                else:
                    errors += 1
                    print(f"  EMPTY_REWRITE article_id={article_id}")
            except Exception as exc:
                errors += 1
                print(f"  FAIL article_id={article_id} - {exc}")

            done += 1
            if done % PROGRESS_EVERY == 0 or done == len(todo):
                conn.commit()
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed else 0
                remaining = (len(todo) - done) / rate if rate else 0
                print(f"  ...{done}/{len(todo)} - {rate:.1f}/s - ~{remaining:.0f}s remaining - {total_tokens} tokens so far")

    conn.commit()
    conn.close()
    print(f"rows examined : {len(todo)}")
    print(f"  filled      : {filled}")
    print(f"  errors      : {errors}")
    print(f"  tokens used : {total_tokens}")


if __name__ == "__main__":
    main()
