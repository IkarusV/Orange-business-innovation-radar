"""End-to-end Innovation Radar pipeline: collect new TED/CORDIS/OCDS articles,
filter obvious noise with the trained ML model, classify what's left with the
NavyAI LLM into opportunity spaces, and write a run summary.

Run from repo root: python run_radar.py [--limit N]
--limit caps how many articles get sent to the LLM this run (passed straight
through to opportunity_classifier.collector.main.run) - useful for a cheap
dry run of the whole pipeline shape without spending real tokens.

This script only orchestrates existing modules; no collection, filtering, or
classification logic lives here. It writes a JSON summary to
logs/radar_runs/ for building a report from afterward - it does not publish
a report itself.
"""
import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from ted_collector.collector import main as ted_main
from cordis_collector.collector import main as cordis_main
from ocds_collector.collector import main as ocds_main
from opportunity_classifier.collector import select_corpus
from opportunity_classifier.mlfilter import main as mlfilter_main
from opportunity_classifier.collector import main as classifier_main
from common.storage import get_connection

REPO_ROOT = Path(__file__).resolve().parent
DB_PATH = REPO_ROOT / "data" / "articles.db"
LOG_PATH = REPO_ROOT / "logs" / "radar_pipeline.log"
SUMMARY_DIR = REPO_ROOT / "logs" / "radar_runs"

ACTIVE_SOURCES = ("ted", "cordis", "ocds_uk", "ocds_ua")


def setup_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
    )
    return logging.getLogger("radar_pipeline")


def article_counts_by_source(conn) -> dict:
    placeholders = ",".join("?" for _ in ACTIVE_SOURCES)
    return dict(conn.execute(
        f"SELECT source_type, COUNT(*) FROM articles WHERE source_type IN ({placeholders}) "
        "GROUP BY source_type",
        ACTIVE_SOURCES,
    ))


def spaces_snapshot(conn) -> dict:
    return {
        (v, uc, t): cnt
        for v, uc, t, cnt in conn.execute(
            "SELECT vertical, use_case_id, technology_id, article_count FROM opportunity_spaces"
        )
    }


def pending_pool_ids(conn) -> set:
    """Pool articles not yet classified, as of right now."""
    already = {r[0] for r in conn.execute("SELECT article_id FROM article_classifications")}
    pool = {r[0] for r in conn.execute("SELECT article_id FROM classification_pool")}
    return pool - already


def ml_gate_split(conn, pending_ids: set) -> dict:
    scores = dict(conn.execute("SELECT article_id, keep_recommended FROM ml_noise_scores"))
    kept = sum(1 for aid in pending_ids if scores.get(aid, 1) == 1)
    deleted = sum(1 for aid in pending_ids if scores.get(aid) == 0)
    unscored = sum(1 for aid in pending_ids if aid not in scores)
    return {"kept": kept, "deleted": deleted, "unscored_kept_by_default": unscored}


def diff_spaces(before: dict, after: dict) -> dict:
    new_spaces = [
        {"vertical": v, "use_case_id": uc, "technology_id": t, "article_count": cnt}
        for (v, uc, t), cnt in after.items() if (v, uc, t) not in before
    ]
    grown_spaces = [
        {"vertical": v, "use_case_id": uc, "technology_id": t,
         "article_count": after[(v, uc, t)], "added": after[(v, uc, t)] - before[(v, uc, t)]}
        for (v, uc, t) in after
        if (v, uc, t) in before and after[(v, uc, t)] > before[(v, uc, t)]
    ]
    new_spaces.sort(key=lambda s: -s["article_count"])
    grown_spaces.sort(key=lambda s: -s["added"])
    return {"new_spaces": new_spaces, "grown_spaces": grown_spaces}


def run(limit=None) -> dict:
    log = setup_logging()
    t_start = time.time()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    conn = get_connection(DB_PATH)
    before_articles = article_counts_by_source(conn)
    before_spaces = spaces_snapshot(conn)
    conn.close()

    log.info("=== Stage 1/5: collect (TED, CORDIS, OCDS) ===")
    ted_main.run()
    cordis_main.run()
    ocds_main.run()

    conn = get_connection(DB_PATH)
    after_collect_articles = article_counts_by_source(conn)
    conn.close()
    new_by_source = {
        s: after_collect_articles.get(s, 0) - before_articles.get(s, 0) for s in ACTIVE_SOURCES
    }
    log.info("collected: %s", new_by_source)

    log.info("=== Stage 2/5: select corpus ===")
    pool_size = select_corpus.run(report_only=False)

    log.info("=== Stage 3/5: ML noise filter ===")
    mlfilter_main.run()

    conn = get_connection(DB_PATH)
    pending_before_classify = pending_pool_ids(conn)
    ml_gate = ml_gate_split(conn, pending_before_classify)
    conn.close()
    log.info(
        "ML gate on %d pending pool articles: keep=%d delete=%d unscored=%d",
        len(pending_before_classify), ml_gate["kept"],
        ml_gate["deleted"], ml_gate["unscored_kept_by_default"],
    )

    log.info("=== Stage 4/5: classify (NavyAI) ===")
    t_before_classify = datetime.now(timezone.utc).isoformat()
    classifier_main.run(limit=limit)

    log.info("=== Stage 5/5: summarize ===")
    conn = get_connection(DB_PATH)
    status_counts = dict(conn.execute(
        "SELECT status, COUNT(*) FROM article_classifications WHERE classified_at >= ? GROUP BY status",
        (t_before_classify,),
    ))
    tokens_this_run = conn.execute(
        "SELECT SUM(tokens_used) FROM article_classifications WHERE classified_at >= ?",
        (t_before_classify,),
    ).fetchone()[0] or 0
    after_spaces = spaces_snapshot(conn)
    conn.close()

    space_deltas = diff_spaces(before_spaces, after_spaces)
    elapsed = time.time() - t_start

    summary = {
        "run_id": run_id,
        "elapsed_seconds": round(elapsed, 1),
        "collected_by_source": new_by_source,
        "pool_size": pool_size,
        "ml_gate": ml_gate,
        "classified_this_run": status_counts,
        "tokens_this_run": tokens_this_run,
        "new_opportunity_spaces": space_deltas["new_spaces"],
        "grown_opportunity_spaces": space_deltas["grown_spaces"],
    }

    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = SUMMARY_DIR / f"{run_id}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    log.info("--- run summary ---")
    log.info("collected: %s", new_by_source)
    log.info("ML filter: kept %d, deleted %d, unscored %d",
              ml_gate["kept"], ml_gate["deleted"], ml_gate["unscored_kept_by_default"])
    log.info("classified this run: %s (%d tokens)", status_counts, tokens_this_run)
    log.info("new opportunity spaces: %d, grown opportunity spaces: %d",
              len(space_deltas["new_spaces"]), len(space_deltas["grown_spaces"]))
    log.info("summary written to %s", summary_path)
    log.info("total wall time %.1fs", elapsed)

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="cap articles sent to the LLM this run")
    args = parser.parse_args()
    run(limit=args.limit)
