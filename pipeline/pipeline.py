import argparse
import os

import yaml

import db
from connectors import navy_search, rss, ted
from dedup import filter_duplicates

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MATRIX_PATH = os.path.join(SCRIPT_DIR, "config", "matrix.yaml")
FEEDS_PATH = os.path.join(SCRIPT_DIR, "config", "flux_rss_innovation_radar.md")


def load_matrix():
    with open(MATRIX_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(connectors, sample_fraction=1.0):
    matrix = load_matrix()
    conn = db.connect()

    verticals = list(matrix["verticals"])
    domains = list(matrix["domains"])
    boosted = db.underrepresented_cells(
        conn, verticals, domains, matrix["search"]["coverage_threshold"]
    )
    all_cells = [(v, d) for v in verticals for d in domains]

    signals = []
    if "rss" in connectors and os.path.exists(FEEDS_PATH):
        signals.extend(rss.collect(FEEDS_PATH))
    if "ted" in connectors:
        signals.extend(ted.collect(
            lookback_days=matrix["search"]["lookback_days"]
        ))
    if "navy" in connectors:
        signals.extend(navy_search.collect(
            matrix, all_cells, set(boosted), sample_fraction=sample_fraction
        ))

    signals = filter_duplicates(signals, conn)
    inserted = db.insert_signals(conn, signals)
    print(f"\nInserted {inserted} new signals "
          f"({len(signals) - inserted} duplicates skipped at insert)")

    print("\nCoverage (least covered cells first):")
    for row in db.coverage(conn)[:15]:
        print(f"  {row['vertical_hint'] or '?':24} x "
              f"{row['domain_hint'] or '?':18} : {row['signal_count']}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Innovation Radar collection pipeline")
    parser.add_argument(
        "--connectors", nargs="+", default=["rss", "ted", "navy"],
        choices=["rss", "ted", "navy"],
        help="Connectors to run",
    )
    parser.add_argument(
        "--sample-fraction", type=float, default=1.0,
        help="Test mode for the navy connector: run only this fraction of the "
             "252-query matrix (e.g. 0.1 for 1/10) and report actual + projected "
             "token usage, without spending the full quota. Default 1.0 (full run).",
    )
    args = parser.parse_args()
    if not (0 < args.sample_fraction <= 1.0):
        parser.error("--sample-fraction must be between 0 (exclusive) and 1")
    run(args.connectors, sample_fraction=args.sample_fraction)
