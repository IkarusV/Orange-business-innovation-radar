"""Fill in signal_type and geography for the placeholder rows written by
_import_all_spaces.py, wherever that can be done for free.

TED, OCDS and CORDIS carry their signal type and country in the record itself
(TED/OCDS: feed identity + a field; CORDIS: a per-project status/participant
lookup against CORDIS's own public API) - no LLM call needed, so this covers
those source types unconditionally, no cost, no confirmation needed.

RSS and Google News have no structured country or signal type on the record;
resolving those genuinely requires the paid Navy classifier and is
deliberately left to a separate, explicitly-approved step.

Run from the repo root with the venv python:
    .venv\\Scripts\\python.exe Pipelineteamfile\\_backfill_deterministic.py
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from opportunity_classifier.collector import main as classifier_main
from opportunity_classifier.collector import signal_route, geo_route, taxonomy as taxonomy_mod
from opportunity_classifier.collector import storage as classifier_storage
from common.storage import get_connection

DB_PATH = HERE / "data" / "articles.db"
TAXONOMY_PATH = HERE / "opportunity_classifier" / "config" / "taxonomy.json"
REQUEST_SPACING_SECONDS = 0.3  # be polite to CORDIS's public API


def load_deterministic_todo(conn):
    """Classified articles from a deterministic source type still missing
    signal_type and/or geography, regardless of classification_pool
    membership. classifier_main.load_untyped()/load_ungeotagged() both gate on
    the pool, which exists only to bound LLM-classification cost - it's not a
    relevant filter for TED/OCDS/CORDIS, which cost nothing to backfill. The
    509 rows _import_all_spaces.py wrote were never added to the pool at all,
    which is why the original pool-gated version of this script silently
    processed 0 rows against real data."""
    placeholders = ",".join("?" for _ in signal_route.DETERMINISTIC_SOURCE_TYPES)
    return conn.execute(
        f"""
        SELECT a.id, a.vertical, a.source_name, a.title, a.summary,
               a.source_type, a.extra, a.published_date, a.collected_at
        FROM articles a
        JOIN article_classifications c ON c.article_id = a.id
        WHERE a.source_type IN ({placeholders})
          AND (c.signal_type IS NULL OR c.regions IS NULL)
        ORDER BY a.id
        """,
        list(signal_route.DETERMINISTIC_SOURCE_TYPES),
    ).fetchall()


def count_llm_only_missing(conn):
    """RSS/GNews classified articles still missing signal_type - not touched
    here, genuinely needs the paid Navy classifier."""
    placeholders = ",".join("?" for _ in signal_route.DETERMINISTIC_SOURCE_TYPES)
    row = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM articles a
        JOIN article_classifications c ON c.article_id = a.id
        WHERE a.source_type NOT IN ({placeholders})
          AND c.signal_type IS NULL
        """,
        list(signal_route.DETERMINISTIC_SOURCE_TYPES),
    ).fetchone()
    return row[0]


def main():
    conn = get_connection(DB_PATH)
    classifier_storage.ensure_schema(conn)
    geography_index = taxonomy_mod.geography_index(TAXONOMY_PATH)
    fetcher = classifier_main._cordis_status_fetcher()

    deterministic_rows = load_deterministic_todo(conn)
    llm_only_missing = count_llm_only_missing(conn)

    typed, geotagged, cordis_lookups_failed = 0, 0, 0
    for i, row in enumerate(deterministic_rows):
        article_id, source_type = row[0], row[5]
        type_assignment = classifier_main.route_signal_type(conn, row, fetcher=fetcher)
        if type_assignment is not None:
            classifier_storage.update_signal_type(conn, article_id, classifier_main.assignment_as_result(type_assignment))
            typed += 1
        elif source_type == "cordis":
            cordis_lookups_failed += 1

        geo_routed = classifier_main.route_geography(conn, row, geography_index, fetcher=fetcher)
        if geo_routed is not None:
            resolution, _assignment = geo_routed
            classifier_storage.update_geography(conn, article_id, resolution)
            geotagged += 1

        if source_type == "cordis" and (i + 1) % 20 == 0:
            conn.commit()
            print(f"  ...{i + 1}/{len(deterministic_rows)} deterministic rows processed")
        if source_type == "cordis":
            time.sleep(REQUEST_SPACING_SECONDS)

    conn.commit()
    n_spaces = classifier_storage.recompute_opportunity_spaces(conn)
    conn.close()

    print(f"deterministic-source rows examined : {len(deterministic_rows)}")
    print(f"  signal_type resolved             : {typed}")
    print(f"  geography resolved                : {geotagged}")
    print(f"  cordis lookups that failed/empty  : {cordis_lookups_failed}")
    print(f"rows still needing the LLM (rss/gnews): {llm_only_missing}")
    print(f"OPPORTUNITY SPACES (total)          : {n_spaces}")


if __name__ == "__main__":
    main()
