"""Selects up to TARGET_PER_VERTICAL articles per vertical as the classification
pool: TED backbone, CORDIS/OCDS fill the remainder, RSS backfills last, gnews
excluded entirely (paused as a source - see dark_corner.md). 2b-filtered,
best-effort 50/25/25 recent/~1y/~5y mix. Writes to the classification_pool
table. Dry-run friendly - run with --report-only to print the composition
without writing anything.
"""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .prefilter_blocklist import passes_blocklist

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = REPO_ROOT / "data" / "articles.db"

TARGET_PER_VERTICAL = 600
RECENT_MAX_DAYS = 180
ONE_YEAR_MAX_DAYS = 640
FIVE_YEAR_MIN_DAYS = 1460

# gnews was paused as a source (reliability) - never a classification candidate.
EXCLUDED_SOURCES = {"gnews"}

# TED is the backbone; CORDIS/OCDS are the new institutional sources filling
# the remainder; RSS (thin, no longer actively collected) backfills last.
SOURCE_PRIORITY = {
    "ted": 0,
    "cordis": 1,
    "ocds_uk": 1,
    "ocds_ua": 1,
    "rss": 2,
    "web_discovery": 2,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS classification_pool (
    article_id INTEGER PRIMARY KEY,
    vertical TEXT NOT NULL,
    source_type TEXT NOT NULL,
    temporal_bucket TEXT NOT NULL,
    passed_blocklist INTEGER NOT NULL,
    selected_at TEXT NOT NULL
);
"""


def bucket_for_age(age_days):
    if age_days is None:
        return "other"
    if age_days <= RECENT_MAX_DAYS:
        return "recent"
    if age_days <= ONE_YEAR_MAX_DAYS:
        return "one_year"
    if age_days >= FIVE_YEAR_MIN_DAYS:
        return "five_year"
    return "other"


def load_candidates(conn, vertical):
    now = datetime.now(timezone.utc)
    rows = conn.execute(
        "SELECT id, source_type, title, summary, published_date, collected_at "
        "FROM articles WHERE vertical = ?",
        (vertical,),
    ).fetchall()

    candidates = []
    for article_id, source_type, title, summary, published_date, collected_at in rows:
        if source_type in EXCLUDED_SOURCES:
            continue
        date_str = published_date or collected_at
        age_days = None
        if date_str:
            try:
                d = datetime.fromisoformat(date_str)
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                age_days = (now - d).days
            except ValueError:
                pass
        candidates.append({
            "id": article_id,
            "source_type": source_type,
            "priority": SOURCE_PRIORITY.get(source_type, 1),
            "bucket": bucket_for_age(age_days),
            "age_days": age_days if age_days is not None else 99999,
            "passed_blocklist": passes_blocklist(title, summary),
        })
    return candidates


def select_for_vertical(candidates, target=TARGET_PER_VERTICAL):
    filtered = [c for c in candidates if c["passed_blocklist"]]
    rejected = [c for c in candidates if not c["passed_blocklist"]]

    def ordered(pool):
        return sorted(pool, key=lambda c: (c["priority"], c["age_days"]))

    pool = ordered(filtered)
    buckets = {"recent": [], "one_year": [], "five_year": [], "other": []}
    for c in pool:
        buckets[c["bucket"]].append(c)

    targets = {
        "recent": round(target * 0.5),
        "one_year": round(target * 0.25),
        "five_year": round(target * 0.25),
    }

    selected = []
    selected_ids = set()
    for key, want in targets.items():
        for c in buckets[key][:want]:
            selected.append(c)
            selected_ids.add(c["id"])

    if len(selected) < target:
        for c in pool:
            if len(selected) >= target:
                break
            if c["id"] not in selected_ids:
                selected.append(c)
                selected_ids.add(c["id"])

    backfilled_from_rejected = 0
    if len(selected) < target:
        for c in ordered(rejected):
            if len(selected) >= target:
                break
            selected.append(c)
            selected_ids.add(c["id"])
            backfilled_from_rejected += 1

    return selected[:target], backfilled_from_rejected, len(filtered), len(candidates)


def run(report_only=False):
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    verticals = [r[0] for r in conn.execute("SELECT DISTINCT vertical FROM articles")]
    now_iso = datetime.now(timezone.utc).isoformat()

    if not report_only:
        # The pool represents the current balanced selection, not an accumulating history.
        conn.execute("DELETE FROM classification_pool")

    print(f"{'vertical':32s} {'total':>6s} {'passed_2b':>10s} {'selected':>9s} "
          f"{'ted':>5s} {'cordis/ocds':>11s} {'rss':>5s} {'recent':>7s} {'1y':>5s} {'5y':>5s} {'other':>6s} {'backfilled':>10s}")

    total_selected = 0
    for vertical in sorted(verticals):
        candidates = load_candidates(conn, vertical)
        selected, backfilled, n_filtered, n_total = select_for_vertical(candidates)

        n_ted = sum(1 for c in selected if c["source_type"] == "ted")
        n_new = sum(1 for c in selected if c["source_type"] in ("cordis", "ocds_uk", "ocds_ua"))
        n_rss = sum(1 for c in selected if c["source_type"] == "rss")
        by_bucket = {"recent": 0, "one_year": 0, "five_year": 0, "other": 0}
        for c in selected:
            by_bucket[c["bucket"]] += 1

        print(f"{vertical:32s} {n_total:6d} {n_filtered:10d} {len(selected):9d} "
              f"{n_ted:5d} {n_new:11d} {n_rss:5d} {by_bucket['recent']:7d} {by_bucket['one_year']:5d} "
              f"{by_bucket['five_year']:5d} {by_bucket['other']:6d} {backfilled:10d}")

        total_selected += len(selected)

        if not report_only:
            conn.executemany(
                "INSERT OR REPLACE INTO classification_pool "
                "(article_id, vertical, source_type, temporal_bucket, passed_blocklist, selected_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(c["id"], vertical, c["source_type"], c["bucket"], int(c["passed_blocklist"]), now_iso)
                 for c in selected],
            )

    if not report_only:
        conn.commit()

    print()
    print(f"Total selected across all verticals: {total_selected}")
    print(f"Estimated tokens at ~1650/call: {total_selected * 1650:,}")
    conn.close()
    return total_selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-only", action="store_true", help="print composition, don't write to DB")
    args = parser.parse_args()
    run(report_only=args.report_only)


if __name__ == "__main__":
    main()
