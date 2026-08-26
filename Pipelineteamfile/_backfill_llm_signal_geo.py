"""Resolve signal_type and geography, via the paid Navy LLM classifier, for the
RSS/Google News rows that _backfill_deterministic.py could not touch for free
(their country and signal type exist nowhere but the free text).

Deliberately mirrors classifier_main.backfill_signal_types() /
backfill_signal_geography(), but:
  - queries classified-but-untyped/ungeotagged rows directly instead of
    through classification_pool (same pool-gating bug that made
    _backfill_deterministic.py's first run a no-op - the 507 bulk-imported
    rows were never added to the pool)
  - makes ONE classify() call per article and applies both the signal_type
    and geography halves of that single result, instead of the two upstream
    functions' combined two calls per article

use_case_id/technology_id/confidence are intentionally NOT written back: this
project's own live classifier might not agree with Project A's already-
computed labels the bulk import carried over, and reconciling that is a
separate decision from filling in the two fields (signal type, geography)
that were simply never in the export. Evidence quality's confidence component
already has a documented fallback for articles with no classifier confidence
(radar_v2/services/attractiveness.py's evidence_quality()) - this script does
not change that.

Run from the repo root with the venv python:
    .venv\\Scripts\\python.exe Pipelineteamfile\\_backfill_llm_signal_geo.py
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from opportunity_classifier.collector import main as classifier_main
from opportunity_classifier.collector import client as classifier_client
from opportunity_classifier.collector import taxonomy as taxonomy_mod
from opportunity_classifier.collector import storage as classifier_storage
from common.storage import get_connection

DB_PATH = HERE / "data" / "articles.db"
TAXONOMY_PATH = HERE / "opportunity_classifier" / "config" / "taxonomy.json"
PROMPT_TEMPLATE_PATH = HERE / "opportunity_classifier" / "config" / "prompt_template.txt"
MAX_WORKERS = 10
PROGRESS_EVERY = 20


def load_todo(conn):
    """Classified RSS/GNews articles still missing signal_type, regardless of
    classification_pool membership."""
    return conn.execute(
        """
        SELECT a.id, a.vertical, a.source_name, a.title, a.summary,
               a.source_type, a.extra, a.published_date, a.collected_at
        FROM articles a
        JOIN article_classifications c ON c.article_id = a.id
        WHERE a.source_type IN ('rss', 'gnews')
          AND c.signal_type IS NULL
        ORDER BY a.id
        """
    ).fetchall()


def main():
    api_key = os.environ.get("NAVY_API_KEY")
    base_url = os.environ.get("NAVY_BASE_URL", "https://api.navy/v1")
    if not api_key:
        raise RuntimeError("NAVY_API_KEY not set in environment")

    taxonomy = taxonomy_mod.load_taxonomy(TAXONOMY_PATH)
    taxonomy_text = taxonomy_mod.taxonomy_block(taxonomy)
    use_case_ids, technology_ids = taxonomy_mod.valid_ids(taxonomy)
    geography_index = taxonomy_mod.geography_index(TAXONOMY_PATH)
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    navy_client = classifier_client.make_client(api_key, base_url)

    conn = get_connection(DB_PATH)
    classifier_storage.ensure_schema(conn)

    todo = load_todo(conn)
    print(f"rows to resolve via LLM: {len(todo)}")

    typed, geotagged, errors, total_tokens = 0, 0, 0, 0
    signal_type_counts, region_counts, unresolved = {}, {}, {}
    done = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(
                classifier_main.classify_one, navy_client, template, taxonomy_text,
                use_case_ids, technology_ids, row, None, geography_index,
            ): row[0]
            for row in todo
        }
        for future in as_completed(futures):
            article_id = futures[future]
            try:
                article_id, result = future.result()

                classifier_storage.update_signal_type(conn, article_id, result)
                typed += 1
                signal_type_counts[result.signal_type] = signal_type_counts.get(result.signal_type, 0) + 1
                if result.signal_type is None:
                    print(f"  SIGNAL_TYPE_UNASSIGNED article_id={article_id} - {result.signal_type_rationale}")

                resolution = geography_index.resolve(
                    result.countries or [], result.region_override,
                    result.geography_confidence or 0.0, result.geography_assigned_by,
                )
                classifier_storage.update_geography(conn, article_id, resolution, tokens=0)
                geotagged += 1
                for region_id in resolution.regions or ("<none>",):
                    region_counts[region_id] = region_counts.get(region_id, 0) + 1
                for token in resolution.unresolved:
                    unresolved[token] = unresolved.get(token, 0) + 1

                total_tokens += result.total_tokens
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
    n_spaces = classifier_storage.recompute_opportunity_spaces(conn)
    conn.close()

    print(f"rows examined       : {len(todo)}")
    print(f"  signal_type set   : {typed}")
    print(f"  geography set     : {geotagged}")
    print(f"  errors            : {errors}")
    print(f"  tokens used       : {total_tokens}")
    print(f"signal type counts  : {signal_type_counts}")
    print(f"region counts       : {region_counts}")
    print(f"unresolved countries: {unresolved}")
    print(f"OPPORTUNITY SPACES (total): {n_spaces}")


if __name__ == "__main__":
    main()
