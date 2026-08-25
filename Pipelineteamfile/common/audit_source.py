"""Record (or update) a source's trust category.

Usage:
    python -m common.audit_source "Reuters" --category wire_service \\
        --auditor "Dan" --notes "Verified as a wire service via its own masthead"

The score/status are never entered directly - they're derived mechanically
from the category via common.trust's anchor table.
"""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .trust import CATEGORY_SLUGS, compute_trust

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "articles.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source_name", help="Exact source_name value as stored in articles.source_name")
    parser.add_argument("--category", required=True, choices=CATEGORY_SLUGS, help="Publisher-type category")
    parser.add_argument("--auditor", required=True, help="Who (or what) performed this audit")
    parser.add_argument("--notes", default=None, help="Optional free-text notes")
    return parser


def record_audit(conn: sqlite3.Connection, source_name: str, category: str,
                  auditor: str, notes: str = None) -> None:
    audited_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO sources (source_name, category, audited_at, auditor, notes)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(source_name) DO UPDATE SET
            category=excluded.category, audited_at=excluded.audited_at,
            auditor=excluded.auditor, notes=excluded.notes
        """,
        (source_name, category, audited_at, auditor, notes),
    )
    conn.commit()


def main() -> None:
    args = build_parser().parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    record_audit(conn, args.source_name, args.category, args.auditor, args.notes)

    row = conn.execute("SELECT * FROM sources WHERE source_name = ?", (args.source_name,)).fetchone()
    result = compute_trust(row)
    conn.close()

    print(f"{args.source_name}: category={result.category} score={result.score}/100 status={result.status}")


if __name__ == "__main__":
    main()
