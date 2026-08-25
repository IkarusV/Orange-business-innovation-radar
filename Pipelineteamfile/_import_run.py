"""One-off bootstrap: seed this project's team DB with raw articles pulled from the
standalone "Pipeline Opportunity" run, then classify them through THIS project's own
live Navy classifier so the app shows real opportunity spaces instead of demo data.

Run from the repo root with the venv python:
    .venv\\Scripts\\python.exe Pipelineteamfile\\_import_run.py <command>

Commands:
    select      pick candidate articles from the export, insert them, build the pool
    classify N  classify at most N pending pool articles via the real Navy API
    status      print pool / classification / opportunity-space counts and token spend
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# The pipeline reads os.environ directly and client.py binds NAVY_MODEL at import
# time, so load the app's .env before importing any pipeline module.
ENV_PATH = REPO_ROOT / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

DB_PATH = HERE / "data" / "articles.db"
EXPORT_DIR = REPO_ROOT / "imports" / "pipeline_opportunity_export"
SELECTION_PATH = EXPORT_DIR / "loaded_selection.json"

TARGET_SPACES = 30          # oversample: aim to land at >= 20 distinct spaces after reclassification
MAX_PER_VERTICAL = 3
EXCLUDED_SOURCE_TYPES = {"gnews"}   # select_corpus.py never pools gnews


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def cmd_select():
    spaces = json.loads((EXPORT_DIR / "opportunity_spaces.json").read_text(encoding="utf-8"))["opportunity_spaces"]
    articles = json.loads((EXPORT_DIR / "articles.json").read_text(encoding="utf-8"))["articles"]

    def usable_articles(space):
        out = []
        for aid in space["linked_article_ids"]:
            art = articles.get(str(aid))
            if not art or art["source_type"] in EXCLUDED_SOURCE_TYPES:
                continue
            if not (art.get("title") or "").strip():
                continue
            out.append(art)
        # richest evidence first: longest summary wins
        out.sort(key=lambda a: -len(a.get("summary") or ""))
        return out

    by_vertical = defaultdict(list)
    for space in spaces:
        if usable_articles(space):
            by_vertical[space["vertical"]].append(space)
    for vertical in by_vertical:
        by_vertical[vertical].sort(key=lambda s: (-(s["article_count"] or 0), s["use_case_id"]))

    # round-robin across verticals, one distinct (use_case, technology) pair each
    chosen, used_pairs, per_vertical = [], set(), defaultdict(int)
    verticals = sorted(by_vertical)
    cursor = {v: 0 for v in verticals}
    while len(chosen) < TARGET_SPACES:
        progressed = False
        for vertical in verticals:
            if len(chosen) >= TARGET_SPACES or per_vertical[vertical] >= MAX_PER_VERTICAL:
                continue
            pool = by_vertical[vertical]
            while cursor[vertical] < len(pool):
                space = pool[cursor[vertical]]
                cursor[vertical] += 1
                pair = (space["use_case_id"], space["technology_id"])
                if pair in used_pairs:
                    continue
                used_pairs.add(pair)
                per_vertical[vertical] += 1
                chosen.append(space)
                progressed = True
                break
        if not progressed:
            break

    # one article per chosen space (two for the biggest spaces), deduped
    candidates, seen_ids = [], set()
    for space in chosen:
        take = 2 if (space["article_count"] or 0) >= 5 else 1
        for art in usable_articles(space)[:take]:
            if art["id"] in seen_ids:
                continue
            seen_ids.add(art["id"])
            candidates.append({"article": art, "space": space})

    from common.models import Article
    from common.storage import get_connection, insert_articles

    now = datetime.now(timezone.utc)
    to_insert = []
    for entry in candidates:
        art = entry["article"]
        extra = None
        if art.get("extra"):
            try:
                extra = json.loads(art["extra"])
            except (json.JSONDecodeError, TypeError):
                extra = {"raw": art["extra"]}
        extra = extra or {}
        extra["imported_from"] = "Pipeline Opportunity export"
        extra["source_article_id"] = art["id"]
        to_insert.append(Article(
            vertical=art["vertical"],
            source_name=art["source_name"],
            source_type=art["source_type"],
            title=art["title"],
            url=art.get("url"),
            guid=art.get("guid"),
            published_date=_parse_dt(art.get("published_date")),
            summary=art.get("summary"),
            collected_at=_parse_dt(art.get("collected_at")) or now,
            confidence=art.get("confidence"),
            extra=extra,
            time_window=art.get("time_window"),
        ))

    conn = get_connection(DB_PATH)
    inserted = insert_articles(conn, to_insert)
    total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    conn.close()

    SELECTION_PATH.write_text(json.dumps({
        "selected_at": now.isoformat(),
        "target_spaces_selected": len(chosen),
        "candidate_articles": len(to_insert),
        "articles_inserted": inserted,
        "articles_in_team_db": total,
        "verticals_covered": sorted({s["vertical"] for s in chosen}),
        "target_spaces": [{
            "source_space_id": s["source_space_id"], "vertical": s["vertical"],
            "use_case_id": s["use_case_id"], "use_case_label": s["use_case_label"],
            "technology_id": s["technology_id"], "technology_label": s["technology_label"],
            "source_article_count": s["article_count"],
        } for s in chosen],
        "candidate_articles_detail": [{
            "source_article_id": e["article"]["id"], "vertical": e["article"]["vertical"],
            "source_type": e["article"]["source_type"], "title": e["article"]["title"],
            "url": e["article"].get("url"),
            "from_source_space_id": e["space"]["source_space_id"],
        } for e in candidates],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"target spaces selected : {len(chosen)} across {len(set(s['vertical'] for s in chosen))} verticals")
    print(f"candidate articles     : {len(to_insert)}")
    print(f"newly inserted         : {inserted}")
    print(f"articles in team DB    : {total}")

    from opportunity_classifier.collector import select_corpus
    pool = select_corpus.run(report_only=False)
    print(f"classification pool    : {pool}")


def cmd_classify(limit):
    from opportunity_classifier.collector import main as classifier_main
    classifier_main.run(limit=limit)


def cmd_status():
    import sqlite3
    if not DB_PATH.exists():
        print("team DB does not exist yet")
        return
    conn = sqlite3.connect(DB_PATH)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def scalar(sql, default=0):
        return conn.execute(sql).fetchone()[0] or default

    print("articles            :", scalar("SELECT COUNT(*) FROM articles"))
    if "classification_pool" in tables:
        print("classification_pool :", scalar("SELECT COUNT(*) FROM classification_pool"))
    if "article_classifications" in tables:
        tokens, rows = conn.execute(
            "SELECT SUM(tokens_used), COUNT(*) FROM article_classifications").fetchone()
        print("classified rows     :", rows)
        print("TOKENS USED (SUM)   :", tokens or 0)
        print("status breakdown    :", dict(conn.execute(
            "SELECT status, COUNT(*) FROM article_classifications GROUP BY status")))
        pending = scalar("SELECT COUNT(*) FROM classification_pool") - (rows or 0)
        print("pending in pool     :", max(pending, 0))
    if "opportunity_spaces" in tables:
        print("OPPORTUNITY SPACES  :", scalar("SELECT COUNT(*) FROM opportunity_spaces"))
        print("spaces by vertical  :", dict(conn.execute(
            "SELECT vertical, COUNT(*) FROM opportunity_spaces GROUP BY 1 ORDER BY 2 DESC")))
    conn.close()


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command == "select":
        cmd_select()
    elif command == "classify":
        cmd_classify(int(sys.argv[2]))
    else:
        cmd_status()
