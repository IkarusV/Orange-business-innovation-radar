"""Fill in signal_type_plain_summary for every already-typed deterministic-
source row (TED, OCDS, CORDIS) - free, no LLM call.

These rows already have a real signal_type from an earlier backfill
(_backfill_deterministic.py); this script just re-runs route_signal_type()
over them so the newly-added plain_summary half of SignalTypeAssignment gets
written too. Re-deriving is safe and idempotent: every other field
route_signal_type() returns is recomputed to the same value it already has.
CORDIS project status is cached in articles.extra from the earlier run, so
this makes zero calls to CORDIS's API.

Run from the repo root with the venv python:
    .venv\\Scripts\\python.exe Pipelineteamfile\\_backfill_plain_summary_deterministic.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from opportunity_classifier.collector import main as classifier_main
from opportunity_classifier.collector import signal_route
from opportunity_classifier.collector import storage as classifier_storage
from common.storage import get_connection

DB_PATH = HERE / "data" / "articles.db"


def load_todo(conn):
    placeholders = ",".join("?" for _ in signal_route.DETERMINISTIC_SOURCE_TYPES)
    return conn.execute(
        f"""
        SELECT a.id, a.vertical, a.source_name, a.title, a.summary,
               a.source_type, a.extra, a.published_date, a.collected_at
        FROM articles a
        JOIN article_classifications c ON c.article_id = a.id
        WHERE a.source_type IN ({placeholders})
          AND c.signal_type IS NOT NULL
          AND c.signal_type_plain_summary IS NULL
        ORDER BY a.id
        """,
        list(signal_route.DETERMINISTIC_SOURCE_TYPES),
    ).fetchall()


def main():
    conn = get_connection(DB_PATH)
    classifier_storage.ensure_schema(conn)
    fetcher = classifier_main._cordis_status_fetcher()

    todo = load_todo(conn)
    print(f"deterministic rows to backfill: {len(todo)}")

    filled, unresolved = 0, 0
    for i, row in enumerate(todo):
        article_id = row[0]
        assignment = classifier_main.route_signal_type(conn, row, fetcher=fetcher)
        if assignment is None:
            unresolved += 1
            continue
        classifier_storage.update_signal_type(conn, article_id, classifier_main.assignment_as_result(assignment))
        filled += 1
        if (i + 1) % 50 == 0:
            conn.commit()
            print(f"  ...{i + 1}/{len(todo)} processed")

    conn.commit()
    conn.close()
    print(f"plain summaries filled: {filled}")
    print(f"unresolved (status lookup unavailable): {unresolved}")


if __name__ == "__main__":
    main()
