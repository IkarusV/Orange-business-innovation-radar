from __future__ import annotations

import json
import sqlite3
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path

from radar_v2.constants import TAXONOMY, TEAM_DB


def _taxonomy() -> tuple[dict[str, str], dict[str, str]]:
    payload = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    return (
        {item["id"]: item["label"] for item in payload["use_cases"]},
        {item["id"]: item["label"] for item in payload["technologies"]},
    )


USE_CASES, TECHNOLOGIES = _taxonomy()

DEMO_OPPORTUNITIES = [
    {
        "id": 1, "vertical": "Manufacturing", "use_case_id": "predictive-maintenance",
        "use_case": "Predictive maintenance", "technology_id": "digital-twin", "technology": "Digital Twin",
        "article_count": 18, "relevance": 88, "confidence": 84, "horizon": "Now", "momentum": "+12%",
        "summary": "Industrial operators are joining asset telemetry, simulation and maintenance planning to reduce unplanned downtime.",
        "updated": "Today",
    },
    {
        "id": 2, "vertical": "Financial services", "use_case_id": "anomaly-detection",
        "use_case": "Threat visibility", "technology_id": "cybersecurity-platform", "technology": "Cybersecurity Platform",
        "article_count": 14, "relevance": 82, "confidence": 76, "horizon": "Next", "momentum": "+8%",
        "summary": "Banks are strengthening network-level visibility as operational resilience requirements move into execution.",
        "updated": "Today",
    },
    {
        "id": 3, "vertical": "Public sector", "use_case_id": "document-processing-extraction",
        "use_case": "Trusted document processing", "technology_id": "generative-ai-llms", "technology": "Generative AI / LLMs",
        "article_count": 11, "relevance": 79, "confidence": 72, "horizon": "Next", "momentum": "+19%",
        "summary": "Public services are testing governed language systems for high-volume citizen and administrative workflows.",
        "updated": "Yesterday",
    },
    {
        "id": 4, "vertical": "Energy & utilities", "use_case_id": "energy-optimization",
        "use_case": "Energy optimization", "technology_id": "edge-computing", "technology": "Edge Computing",
        "article_count": 9, "relevance": 74, "confidence": 68, "horizon": "Later", "momentum": "+6%",
        "summary": "Distributed control and local intelligence are emerging as grid flexibility becomes more valuable.",
        "updated": "2 days ago",
    },
]

DEMO_EVIDENCE = [
    {"title": "European industrial digitalisation programme", "source": "European Commission", "source_type": "CORDIS", "url": "https://cordis.europa.eu/", "date": "2026", "excerpt": "Funding activity connects industrial data, resilient operations and advanced automation.", "confidence": 88},
    {"title": "Connected maintenance services procurement", "source": "Tenders Electronic Daily", "source_type": "TED", "url": "https://ted.europa.eu/", "date": "2026", "excerpt": "A European procurement notice seeks connected monitoring and maintenance capabilities.", "confidence": 82},
]


def _connect(path: Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(path or TEAM_DB)
    connection.row_factory = sqlite3.Row
    return connection


def database_ready() -> bool:
    if not TEAM_DB.exists():
        return False
    with _connect() as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return "opportunity_spaces" in tables and "articles" in tables


def list_opportunities() -> list[dict]:
    if not database_ready():
        return DEMO_OPPORTUNITIES
    with _connect() as connection:
        rows = connection.execute(
            """SELECT id,vertical,use_case_id,technology_id,article_count,avg_client_relevance,last_updated_at
            FROM opportunity_spaces ORDER BY COALESCE(avg_client_relevance,0) DESC,article_count DESC"""
        ).fetchall()
    if not rows:
        return DEMO_OPPORTUNITIES
    output = []
    max_count = max(row["article_count"] for row in rows) or 1
    for row in rows:
        relevance = round((row["avg_client_relevance"] or min(row["article_count"] / max_count, 1)) * 100)
        confidence = min(96, 48 + row["article_count"] * 4)
        output.append({
            "id": row["id"], "vertical": row["vertical"], "use_case_id": row["use_case_id"],
            "use_case": USE_CASES.get(row["use_case_id"], row["use_case_id"].replace("-", " ").title()),
            "technology_id": row["technology_id"],
            "technology": TECHNOLOGIES.get(row["technology_id"], row["technology_id"].replace("-", " ").title()),
            "article_count": row["article_count"], "relevance": relevance, "confidence": confidence,
            "horizon": "Now" if relevance >= 82 else "Next" if relevance >= 68 else "Later",
            "momentum": f"+{min(24, max(3, row['article_count'] * 2))}%",
            "summary": f"{row['article_count']} institutional signals connect {USE_CASES.get(row['use_case_id'], row['use_case_id'])} with {TECHNOLOGIES.get(row['technology_id'], row['technology_id'])} in {row['vertical']}.",
            "updated": (row["last_updated_at"] or "Recently")[:10],
        })
    return output


def opportunity_detail(opportunity_id: int) -> tuple[dict, list[dict]]:
    opportunities = list_opportunities()
    opportunity = next((item for item in opportunities if item["id"] == opportunity_id), opportunities[0])
    if not database_ready() or opportunity in DEMO_OPPORTUNITIES:
        return opportunity, DEMO_EVIDENCE
    with _connect() as connection:
        row = connection.execute("SELECT linked_article_ids FROM opportunity_spaces WHERE id=?", (opportunity_id,)).fetchone()
        ids = json.loads(row[0]) if row else []
        if not ids:
            return opportunity, []
        placeholders = ",".join("?" for _ in ids)
        articles = connection.execute(
            f"""SELECT a.title,a.source_name,a.source_type,a.url,a.published_date,a.summary,c.confidence
            FROM articles a LEFT JOIN article_classifications c ON c.article_id=a.id
            WHERE a.id IN ({placeholders}) ORDER BY a.published_date DESC""", ids
        ).fetchall()
    evidence = [{
        "title": row["title"], "source": row["source_name"], "source_type": row["source_type"].upper(),
        "url": row["url"] or "", "date": (row["published_date"] or "")[:10],
        "excerpt": row["summary"] or "Supporting institutional signal.",
        "confidence": round((row["confidence"] or 0.5) * 100),
    } for row in articles]
    return opportunity, evidence


def dashboard_metrics() -> dict:
    opportunities = list_opportunities()
    if not database_ready():
        return {"opportunities": len(opportunities), "signals": 52, "sources": 4, "verticals": 4, "review": 7}
    with _connect() as connection:
        signals = connection.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        sources = connection.execute("SELECT COUNT(DISTINCT source_type) FROM articles").fetchone()[0]
        verticals = connection.execute("SELECT COUNT(DISTINCT vertical) FROM articles").fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        review = connection.execute("SELECT COUNT(*) FROM article_classifications WHERE status='needs_review'").fetchone()[0] if "article_classifications" in tables else 0
    return {"opportunities": len(opportunities), "signals": signals, "sources": sources, "verticals": verticals, "review": review}


def source_summary() -> list[dict]:
    colors = {"ted": "#ff7900", "cordis": "#7c5cff", "ocds_uk": "#30b77a", "ocds_ua": "#3f8cff"}
    labels = {"ted": "European procurement", "cordis": "EU research programmes", "ocds_uk": "UK procurement", "ocds_ua": "Ukraine procurement"}
    if not database_ready():
        return [{"source": key, "label": labels[key], "count": count, "accent": colors[key]} for key, count in (("ted", 24), ("cordis", 12), ("ocds_uk", 9), ("ocds_ua", 7))]
    with _connect() as connection:
        counts = dict(connection.execute("SELECT source_type,COUNT(*) FROM articles GROUP BY source_type"))
    return [{"source": key, "label": labels.get(key, key.replace("_", " ").title()), "count": value, "accent": colors.get(key, "#8a8a8a")} for key, value in counts.items()]


def latest_run() -> dict:
    summary_dir = TEAM_DB.parent.parent / "logs" / "radar_runs"
    files = sorted(summary_dir.glob("*.json"), reverse=True) if summary_dir.exists() else []
    if not files:
        return {"run_id": "Ready", "elapsed_seconds": 0, "tokens_this_run": 0, "pool_size": 0}
    return json.loads(files[0].read_text(encoding="utf-8"))


def pipeline_preflight(limit: int) -> dict:
    """Estimate the classifier work without starting collection or API calls."""
    if not TEAM_DB.exists() or not database_ready():
        return {"articles": 0, "classification_calls": 0, "pool": 0, "ml_scored": 0, "spaces": 0}
    with _connect() as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        pool = connection.execute("SELECT COUNT(*) FROM classification_pool").fetchone()[0] if "classification_pool" in tables else 0
        classified = connection.execute("SELECT COUNT(*) FROM article_classifications").fetchone()[0] if "article_classifications" in tables else 0
        pending = max(pool - classified, 0)
        ml_scored = connection.execute("SELECT COUNT(*) FROM ml_noise_scores").fetchone()[0] if "ml_noise_scores" in tables else 0
        spaces = connection.execute("SELECT COUNT(*) FROM opportunity_spaces").fetchone()[0] if "opportunity_spaces" in tables else 0
    selected = min(max(int(limit), 1), pending) if pending else 0
    return {"articles": selected, "classification_calls": selected, "pool": pool, "ml_scored": ml_scored, "spaces": spaces}


def all_verticals() -> list[str]:
    mapping = TEAM_DB.parent.parent / "ted_collector" / "config" / "mapping.yaml"
    return list(yaml.safe_load(mapping.read_text(encoding="utf-8")).keys())


def import_external_signals(results: list[dict], vertical: str, source_name: str = "Focused discovery") -> int:
    """Insert external evidence at the team pipeline's article boundary."""
    TEAM_DB.parent.mkdir(parents=True, exist_ok=True)
    team_root = str(TEAM_DB.parent.parent)
    if team_root not in sys.path:
        sys.path.insert(0, team_root)
    from common.models import Article
    from common.storage import get_connection, insert_articles

    now = datetime.now(timezone.utc)
    articles = [Article(
        vertical=vertical,
        source_name=source_name,
        source_type="web_discovery",
        title=item["title"],
        url=item["url"],
        guid=None,
        published_date=None,
        summary=item["excerpt"],
        collected_at=now,
        confidence="mid",
        extra={"engine": item.get("source", "Web"), "returned_date": item.get("date", "")},
        time_window="recent",
    ) for item in results if item.get("url")]
    connection = get_connection(TEAM_DB)
    inserted = insert_articles(connection, articles)
    connection.close()
    return inserted
