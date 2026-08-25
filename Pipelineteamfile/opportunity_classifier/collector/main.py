import argparse
import logging
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import client as classifier_client
from . import geo_route
from . import signal_route
from . import storage as classifier_storage
from . import taxonomy as taxonomy_mod
from ..mlfilter import storage as mlfilter_storage
from common.business_domains import format_coverage_report
from common.geography import format_coverage_report as format_geography_report
from common.personas import format_coverage_report as format_persona_report
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


POOL_QUERY = """
    SELECT a.id, a.vertical, a.source_name, a.title, a.summary,
           a.source_type, a.extra, a.published_date, a.collected_at
    FROM articles a
    JOIN classification_pool p ON p.article_id = a.id
    LEFT JOIN ml_noise_scores n ON n.article_id = a.id
    WHERE n.article_id IS NULL OR n.keep_recommended = 1
    ORDER BY a.id
"""


def load_unclassified(conn: sqlite3.Connection, limit=None):
    """Pool articles not yet classified, minus anything the ML noise filter
    recommends deleting. An article with no ml_noise_scores row (never
    scored - e.g. RSS, which the filter doesn't cover, or brand new rows
    scored between pipeline stages) is kept by default: an absent score is
    never treated as a delete signal.
    """
    already = classifier_storage.already_classified_ids(conn)
    rows = conn.execute(POOL_QUERY).fetchall()
    todo = [r for r in rows if r[0] not in already]
    if limit:
        todo = todo[:limit]
    return todo


def load_untyped(conn: sqlite3.Connection, limit=None):
    """Pool articles already classified against the taxonomy but carrying no
    signal type - rows written before the signal-type fields existed. These
    only need the type backfilled, not a full reclassification."""
    typed = classifier_storage.already_typed_ids(conn)
    classified = classifier_storage.already_classified_ids(conn)
    rows = conn.execute(POOL_QUERY).fetchall()
    todo = [r for r in rows if r[0] in classified and r[0] not in typed]
    if limit:
        todo = todo[:limit]
    return todo


def load_ungeotagged(conn: sqlite3.Connection, limit=None):
    """Pool articles already classified against the taxonomy but carrying no
    resolved geography - rows written before the geography fields existed. These
    only need geography backfilled, not a full reclassification."""
    geotagged = classifier_storage.already_geotagged_ids(conn)
    classified = classifier_storage.already_classified_ids(conn)
    rows = conn.execute(POOL_QUERY).fetchall()
    todo = [r for r in rows if r[0] in classified and r[0] not in geotagged]
    if limit:
        todo = todo[:limit]
    return todo


def route_signal_type(conn: sqlite3.Connection, row, fetcher=None):
    """Deterministic signal type for this article, or None when it has to go
    to the LLM. TED/OCDS/SAM.gov are fixed by feed identity; CORDIS needs the
    project's own status, which the search API does not return, so it is
    looked up once per project and cached into articles.extra."""
    article_id, _vertical, _source_name, _title, _summary, source_type, extra, published_date, collected_at = row
    if source_type not in signal_route.DETERMINISTIC_SOURCE_TYPES:
        return None
    cordis_status = None
    if source_type == "cordis" and fetcher is not None:
        cordis_status = signal_route.cordis_status_for(
            conn, article_id, signal_route.load_extra(extra), fetcher
        )
    return signal_route.route(
        source_type, extra=extra, published_date=published_date,
        collected_at=collected_at, cordis_status=cordis_status,
    )


def route_geography(conn: sqlite3.Connection, row, index, fetcher=None):
    """Deterministic geography for this article, or None when it has to go to
    the LLM. TED/OCDS/SAM.gov carry the country as a field; CORDIS needs the
    project's participant list, which the search API does not return, so it is
    looked up once per project and cached into articles.extra alongside the
    status the signal-type routing already caches there."""
    article_id, _vertical, _source_name, _title, _summary, source_type, extra, _published, _collected = row
    if source_type not in geo_route.DETERMINISTIC_SOURCE_TYPES:
        return None
    cordis_status = None
    if source_type == "cordis" and fetcher is not None:
        cordis_status = geo_route.cordis_participants_for(
            conn, article_id, signal_route.load_extra(extra), fetcher
        )
    return geo_route.resolve(index, source_type, extra, cordis_status)


def classify_one(navy_client, template, taxonomy_text, use_case_ids, technology_ids, row,
                 client_context, geography_index=None):
    article_id, vertical, source_name, title, summary, _source_type, _extra, published_date, _collected_at = row
    result = classifier_client.classify(
        navy_client, template, taxonomy_text, use_case_ids, technology_ids,
        vertical, source_name, title, summary, client_context, published_date,
        geography_index,
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
    geography_index = taxonomy_mod.geography_index(TAXONOMY_PATH)
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")

    navy_client = classifier_client.make_client(api_key, base_url)

    conn = get_connection(DB_PATH)
    classifier_storage.ensure_schema(conn)
    mlfilter_storage.ensure_schema(conn)  # so the ML-filter gate below works even if mlfilter hasn't run yet

    todo = load_unclassified(conn, limit=limit)
    log.info("Starting classification run: %d articles to classify", len(todo))

    done = 0
    status_counts = {}
    signal_type_counts = {}
    total_tokens = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(
                classify_one, navy_client, template, taxonomy_text,
                use_case_ids, technology_ids, row, client_context, geography_index,
            ): row
            for row in todo
        }
        for future in as_completed(futures):
            row = futures[future]
            article_id = row[0]
            try:
                article_id, result = future.result()
                _apply_deterministic_type(conn, row, result, log)
                _apply_deterministic_geography(conn, row, result, geography_index, log)
                classifier_storage.upsert_classification(conn, article_id, result, client_context_ref)
                status_counts[result.status] = status_counts.get(result.status, 0) + 1
                signal_type_counts[result.signal_type] = signal_type_counts.get(result.signal_type, 0) + 1
                total_tokens += result.total_tokens
                if result.signal_type is None:
                    log.warning("SIGNAL_TYPE_UNASSIGNED article_id=%s - %s", article_id, result.signal_type_rationale)
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
    log.info("Classification done: %s - signal types %s - %d tokens this run",
             status_counts, signal_type_counts, total_tokens)

    n_spaces = classifier_storage.recompute_opportunity_spaces(conn)
    log.info("Recomputed %d opportunity spaces", n_spaces)

    print_summary(conn, log)
    conn.close()


def _apply_deterministic_type(conn: sqlite3.Connection, row, result, log) -> None:
    """A known institutional feed's signal type overrides whatever the model
    returned for it. The taxonomy half of the call is still the model's - only
    the signal type is mechanical here."""
    try:
        assignment = route_signal_type(conn, row, fetcher=_cordis_status_fetcher())
    except Exception as exc:
        log.warning("SIGNAL_ROUTE_FAILED article_id=%s - %s", row[0], exc)
        return
    if assignment is None:
        return
    result.signal_type = assignment.signal_type
    result.signal_type_confidence = assignment.signal_type_confidence
    result.signal_date = assignment.signal_date or result.signal_date
    result.event_date = assignment.event_date
    result.event_date_precision = assignment.event_date_precision
    result.signal_type_rationale = assignment.signal_type_rationale
    result.signal_type_assigned_by = assignment.assigned_by


def _apply_deterministic_geography(conn: sqlite3.Connection, row, result, index, log) -> None:
    """A structured source's own country field overrides whatever the model
    inferred for it. The model is only the authority on geography for RSS and
    GNews, where the country exists nowhere but the free text."""
    try:
        routed = route_geography(conn, row, index, fetcher=_cordis_status_fetcher())
    except Exception as exc:
        log.warning("GEO_ROUTE_FAILED article_id=%s - %s", row[0], exc)
        return
    if routed is None:
        return
    resolution, assignment = routed
    result.countries = list(resolution.countries)
    result.regions = list(resolution.regions)
    result.region_override = resolution.region_override or None
    result.geography_confidence = resolution.confidence
    result.geography_assigned_by = resolution.assigned_by
    result.unresolved_countries = list(resolution.unresolved)
    if resolution.unresolved:
        log.warning(
            "GEO_UNRESOLVED article_id=%s field=%s tokens=%s - no region in taxonomy.json",
            row[0], assignment.source_field, list(resolution.unresolved),
        )


def _cordis_status_fetcher():
    from cordis_collector.collector.fetch import fetch_project_status
    return fetch_project_status


def backfill_signal_types(limit=None) -> dict:
    """Add signal types to rows classified before these fields existed, without
    re-running the taxonomy classification they already carry. Deterministic
    sources cost nothing; RSS rows go through one LLM call each.
    """
    log = setup_logging()
    api_key = os.environ.get("NAVY_API_KEY")
    base_url = os.environ.get("NAVY_BASE_URL", "https://api.navy/v1")

    taxonomy = taxonomy_mod.load_taxonomy(TAXONOMY_PATH)
    taxonomy_text = taxonomy_mod.taxonomy_block(taxonomy)
    use_case_ids, technology_ids = taxonomy_mod.valid_ids(taxonomy)
    geography_index = taxonomy_mod.geography_index(TAXONOMY_PATH)
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")

    conn = get_connection(DB_PATH)
    classifier_storage.ensure_schema(conn)
    mlfilter_storage.ensure_schema(conn)

    todo = load_untyped(conn, limit=limit)
    deterministic, llm_rows = [], []
    for row in todo:
        assignment = route_signal_type(conn, row, fetcher=_cordis_status_fetcher())
        if assignment is not None:
            deterministic.append((row[0], assignment))
        else:
            llm_rows.append(row)
    conn.commit()
    log.info("Signal-type backfill: %d rows - %d deterministic, %d need an LLM call",
             len(todo), len(deterministic), len(llm_rows))

    counts, total_tokens, errors = {}, 0, 0
    for article_id, assignment in deterministic:
        classifier_storage.update_signal_type(conn, article_id, assignment_as_result(assignment))
        counts[assignment.signal_type] = counts.get(assignment.signal_type, 0) + 1
    conn.commit()

    if llm_rows:
        if not api_key:
            raise RuntimeError("NAVY_API_KEY not set in environment")
        navy_client = classifier_client.make_client(api_key, base_url)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {
                ex.submit(
                    classify_one, navy_client, template, taxonomy_text,
                    use_case_ids, technology_ids, row, None, geography_index,
                ): row[0]
                for row in llm_rows
            }
            for future in as_completed(futures):
                article_id = futures[future]
                try:
                    article_id, result = future.result()
                    classifier_storage.update_signal_type(conn, article_id, result)
                    counts[result.signal_type] = counts.get(result.signal_type, 0) + 1
                    total_tokens += result.total_tokens
                    if result.signal_type is None:
                        log.warning("SIGNAL_TYPE_UNASSIGNED article_id=%s - %s", article_id, result.signal_type_rationale)
                except Exception as exc:
                    errors += 1
                    log.error("FAIL article_id=%s - %s", article_id, exc)
        conn.commit()

    n_spaces = classifier_storage.recompute_opportunity_spaces(conn)
    conn.close()
    summary = {
        "rows": len(todo), "deterministic": len(deterministic), "llm": len(llm_rows),
        "signal_types": counts, "tokens": total_tokens, "errors": errors, "spaces": n_spaces,
    }
    log.info("Signal-type backfill done: %s", summary)
    return summary


def assignment_as_result(assignment):
    """Adapt a deterministic SignalTypeAssignment to the field names
    update_signal_type expects from a ClassificationResult."""
    return classifier_client.ClassificationResult(
        use_case_id=None, technology_id=None, confidence=None, evidence="", status="classified",
        signal_type=assignment.signal_type,
        signal_type_confidence=assignment.signal_type_confidence,
        signal_date=assignment.signal_date,
        event_date=assignment.event_date,
        event_date_precision=assignment.event_date_precision,
        signal_type_rationale=assignment.signal_type_rationale,
        signal_type_assigned_by=assignment.assigned_by,
        total_tokens=0,
    )


def backfill_business_domains() -> dict:
    """Derive business domains for every existing opportunity space from the
    mapping tables in taxonomy.json. Deterministic and idempotent: no LLM
    calls, no reclassification, safe to re-run after any mapping correction."""
    log = setup_logging()
    conn = get_connection(DB_PATH)
    classifier_storage.ensure_schema(conn)
    report = classifier_storage.backfill_business_domains(conn)
    conn.close()
    for line in format_coverage_report(taxonomy_mod.domain_index(), report):
        log.info("%s", line)
    return report


def backfill_target_personas() -> dict:
    """Derive target persona weights for every existing opportunity space from
    the weight tables and suppression list in taxonomy.json. Deterministic and
    idempotent: no LLM calls, no reclassification, safe to re-run after any
    correction to those tables."""
    log = setup_logging()
    conn = get_connection(DB_PATH)
    classifier_storage.ensure_schema(conn)
    report = classifier_storage.backfill_target_personas(conn)
    conn.close()
    for line in format_persona_report(taxonomy_mod.persona_index(), report):
        log.info("%s", line)
    return report


def backfill_signal_geography(limit=None, deterministic_only=False) -> dict:
    """Resolve geography for rows classified before these fields existed,
    without re-running the taxonomy classification they already carry.

    Structured sources (TED, OCDS, CORDIS, SAM.gov) cost nothing - their country
    is read off the record. RSS rows go through one LLM call each, which is the
    only place in this task that spends anything. --deterministic-only stops
    before the LLM half, so the free structured-source work can be run and
    inspected on its own.
    """
    log = setup_logging()
    api_key = os.environ.get("NAVY_API_KEY")
    base_url = os.environ.get("NAVY_BASE_URL", "https://api.navy/v1")

    taxonomy = taxonomy_mod.load_taxonomy(TAXONOMY_PATH)
    taxonomy_text = taxonomy_mod.taxonomy_block(taxonomy)
    use_case_ids, technology_ids = taxonomy_mod.valid_ids(taxonomy)
    geography_index = taxonomy_mod.geography_index(TAXONOMY_PATH)
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")

    conn = get_connection(DB_PATH)
    classifier_storage.ensure_schema(conn)
    mlfilter_storage.ensure_schema(conn)

    todo = load_ungeotagged(conn, limit=limit)
    deterministic, llm_rows, unresolved = [], [], {}
    for row in todo:
        try:
            routed = route_geography(conn, row, geography_index, fetcher=_cordis_status_fetcher())
        except Exception as exc:
            log.warning("GEO_ROUTE_FAILED article_id=%s - %s", row[0], exc)
            routed = None
        if routed is None:
            llm_rows.append(row)
            continue
        resolution, assignment = routed
        deterministic.append((row[0], resolution))
        for token in resolution.unresolved:
            unresolved[token] = unresolved.get(token, 0) + 1
            log.warning(
                "GEO_UNRESOLVED article_id=%s field=%s token=%s - no region in taxonomy.json",
                row[0], assignment.source_field, token,
            )
    conn.commit()
    log.info("Geography backfill: %d rows - %d deterministic, %d need an LLM call",
             len(todo), len(deterministic), len(llm_rows))

    counts, total_tokens, errors = {}, 0, 0
    for article_id, resolution in deterministic:
        classifier_storage.update_geography(conn, article_id, resolution)
        for region_id in resolution.regions or ("<none>",):
            counts[region_id] = counts.get(region_id, 0) + 1
    conn.commit()

    if llm_rows and not deterministic_only:
        if not api_key:
            raise RuntimeError("NAVY_API_KEY not set in environment")
        navy_client = classifier_client.make_client(api_key, base_url)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {
                ex.submit(
                    classify_one, navy_client, template, taxonomy_text,
                    use_case_ids, technology_ids, row, None, geography_index,
                ): row[0]
                for row in llm_rows
            }
            for future in as_completed(futures):
                article_id = futures[future]
                try:
                    article_id, result = future.result()
                    resolution = geography_index.resolve(
                        result.countries or [], result.region_override,
                        result.geography_confidence or 0.0, result.geography_assigned_by,
                    )
                    classifier_storage.update_geography(
                        conn, article_id, resolution, tokens=result.total_tokens
                    )
                    for region_id in resolution.regions or ("<none>",):
                        counts[region_id] = counts.get(region_id, 0) + 1
                    for token in resolution.unresolved:
                        unresolved[token] = unresolved.get(token, 0) + 1
                    total_tokens += result.total_tokens
                except Exception as exc:
                    errors += 1
                    log.error("FAIL article_id=%s - %s", article_id, exc)
        conn.commit()

    n_spaces = classifier_storage.recompute_opportunity_spaces(conn)
    confidence = classifier_storage.geography_confidence_report(conn)
    conn.close()
    summary = {
        "rows": len(todo), "deterministic": len(deterministic),
        "llm": 0 if deterministic_only else len(llm_rows),
        "llm_skipped": len(llm_rows) if deterministic_only else 0,
        "regions": counts, "unresolved_countries": unresolved,
        "tokens": total_tokens, "errors": errors, "spaces": n_spaces,
        "confidence": confidence,
    }
    log.info("Geography backfill done: %s", summary)
    return summary


def backfill_geography() -> dict:
    """Aggregate geography onto every existing opportunity space from the
    per-signal countries already resolved on its articles. Deterministic and
    idempotent: no LLM calls, no re-extraction, safe to re-run after any
    correction to the region tables in taxonomy.json."""
    log = setup_logging()
    conn = get_connection(DB_PATH)
    classifier_storage.ensure_schema(conn)
    report = classifier_storage.backfill_geography(conn)
    conn.close()
    for line in format_geography_report(taxonomy_mod.geography_index(), report):
        log.info("%s", line)
    return report


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

    log.info("Signal types (assigned_by):")
    for signal_type, assigned_by, count in conn.execute(
        "SELECT signal_type, signal_type_assigned_by, COUNT(*) FROM article_classifications "
        "GROUP BY 1, 2 ORDER BY 3 DESC"
    ):
        log.info("  %s (%s): %d", signal_type, assigned_by, count)

    log.info("Opportunity spaces by horizon:")
    for horizon, rule, count in conn.execute(
        "SELECT horizon, horizon_rule, COUNT(*) FROM opportunity_spaces GROUP BY 1, 2 ORDER BY 3 DESC"
    ):
        log.info("  %s [%s]: %d", horizon, rule, count)

    index = taxonomy_mod.domain_index()
    for line in format_coverage_report(index, classifier_storage.domain_coverage(conn)):
        log.info("%s", line)

    for line in format_persona_report(
        taxonomy_mod.persona_index(), classifier_storage.persona_coverage(conn)
    ):
        log.info("%s", line)

    for line in format_geography_report(
        taxonomy_mod.geography_index(), classifier_storage.geography_coverage(conn)
    ):
        log.info("%s", line)
    for assigned_by, bucket in sorted(classifier_storage.geography_confidence_report(conn).items()):
        log.info(
            "  Geography %s: %d signal(s) - %d with countries, %d empty, %d region_override; "
            "%d below the 0.5 gate (%.1f%%), of which %d actually carry geography (%.1f%% of tagged)",
            assigned_by, bucket["signals"], bucket["with_countries"], bucket["empty_countries"],
            bucket["global_override"], bucket["low_confidence"],
            bucket["low_confidence_share"] * 100, bucket["low_confidence_tagged"],
            bucket["low_confidence_tagged_share"] * 100,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="classify at most N unclassified articles")
    parser.add_argument("--client-context", type=str, default=None, help="path to a client-context file")
    parser.add_argument(
        "--backfill-signal-types", action="store_true",
        help="only add signal types to already-classified rows that lack them",
    )
    parser.add_argument(
        "--backfill-domains", action="store_true",
        help="only derive business domains for existing opportunity spaces (no API calls)",
    )
    parser.add_argument(
        "--backfill-personas", action="store_true",
        help="only derive target persona weights for existing opportunity spaces (no API calls)",
    )
    parser.add_argument(
        "--backfill-signal-geography", action="store_true",
        help="only resolve per-signal geography for already-classified rows that lack it",
    )
    parser.add_argument(
        "--deterministic-only", action="store_true",
        help="with --backfill-signal-geography: skip the RSS/GNews LLM half (no API calls)",
    )
    parser.add_argument(
        "--backfill-geography", action="store_true",
        help="only aggregate geography onto existing opportunity spaces (no API calls)",
    )
    args = parser.parse_args()
    if args.backfill_geography:
        import json as _json
        print(_json.dumps(backfill_geography(), indent=2))
    elif args.backfill_signal_geography:
        import json as _json
        print(_json.dumps(backfill_signal_geography(
            limit=args.limit, deterministic_only=args.deterministic_only,
        ), indent=2))
    elif args.backfill_personas:
        import json as _json
        print(_json.dumps(backfill_target_personas(), indent=2))
    elif args.backfill_domains:
        import json as _json
        print(_json.dumps(backfill_business_domains(), indent=2))
    elif args.backfill_signal_types:
        import json as _json
        print(_json.dumps(backfill_signal_types(limit=args.limit), indent=2))
    else:
        run(limit=args.limit, client_context_path=args.client_context)
