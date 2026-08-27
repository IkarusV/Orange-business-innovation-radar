from __future__ import annotations

import json
import sqlite3
import sys
import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path

from radar_v2.constants import TAXONOMY, TEAM_DB
from radar_v2.services import (
    attractiveness,
    domains as domain_service,
    explanations as explanation_service,
    extension_store,
    geography as geography_service,
    horizon as horizon_service,
    personas as persona_service,
)


def _taxonomy() -> tuple[dict[str, str], dict[str, str]]:
    payload = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    return (
        {item["id"]: item["label"] for item in payload["use_cases"]},
        {item["id"]: item["label"] for item in payload["technologies"]},
    )


USE_CASES, TECHNOLOGIES = _taxonomy()


def _demo_horizon(now: int, sources: int, next_count: int, later: int) -> dict:
    """Demo counterparts of the real horizon fields, built through the same
    formatter the live path uses so the placeholder can never describe a shape
    the real one doesn't produce."""
    verdict = horizon_service.HorizonVerdict(
        horizon="", rule="", reason="", now_count=now, next_count=next_count,
        later_count=later, distinct_sources=sources,
    )
    return {"horizon_breakdown": horizon_service.breakdown_rows(verdict)}


def _demo_gate(independent_sources: int, independent_events: int, confidence: int) -> dict:
    """Demo counterpart of the real Radar/Watchlist gate, built through the
    same functions the live path uses so the placeholder can never show a gate
    outcome or breakdown shape the real one wouldn't produce."""
    return {
        "publication_status": attractiveness.radar_watchlist_gate(independent_sources, independent_events, confidence),
        "gate_breakdown": attractiveness.gate_breakdown_rows(independent_sources, independent_events, confidence),
    }


def _domain_fields(primary: str, domain_ids: list[str]) -> dict:
    """The four UI-facing domain fields: ids drive filtering, labels drive
    display, and the primary drives single-value badges."""
    return {
        "primary_domain": primary,
        "primary_domain_label": domain_service.DOMAIN_LABELS.get(primary, ""),
        "domains": domain_ids,
        "domain_labels": domain_service.labels(domain_ids),
    }


def _persona_fields(weights: list[dict]) -> dict:
    """The two UI-facing persona fields: the weighted rows drive ranking and the
    explainability badge, the id list drives multi-select filtering at the
    default threshold."""
    return {
        "persona_weights": weights,
        "persona_ids": [
            entry["id"] for entry in weights
            if entry["weight"] >= persona_service.DEFAULT_WEIGHT_THRESHOLD
        ],
    }


def _geography_fields(primary: str, region_ids: list[str], country_codes: list[str]) -> dict:
    """The five UI-facing geography fields: region ids drive filtering, labels
    drive display, the primary drives single-value badges, and the country codes
    are what the detail panel shows behind a region."""
    return {
        "primary_region": primary,
        "primary_region_label": geography_service.primary_label(primary),
        "regions": region_ids,
        "region_labels": geography_service.labels(region_ids),
        "countries": geography_service.country_labels(country_codes),
    }


DEMO_SIGNAL_MIX = [
    {"key": "buying_signal", "label": "Buying signal", "value": 3,
     "question": "Is a named organisation currently spending or committing money on this?"},
    {"key": "competitor_move", "label": "Competitor move", "value": 2,
     "question": "Did a named vendor, competitor or peer organisation launch, acquire or announce something?"},
]

DEMO_OPPORTUNITIES = [
    {
        "id": 1, "vertical": "Manufacturing", "use_case_id": "predictive-maintenance",
        "use_case": "Predictive maintenance", "technology_id": "digital-twin", "technology": "Digital Twin",
        "article_count": 18, "relevance": 88, "confidence": 84, "horizon": "Now",
        "horizon_reason": "4 concrete signals across 3 sources, 2 within 90 days",
        "horizon_rule": "Converging concrete evidence", "momentum": "+12%",
        "summary": "Industrial operators are joining asset telemetry, simulation and maintenance planning to reduce unplanned downtime.",
        "updated": "Today", "breakdown": [], "signal_mix": DEMO_SIGNAL_MIX, "orange_fit_score": 72,
        **_demo_horizon(4, 3, 6, 8), **_demo_gate(3, 4, 84),
    },
    {
        "id": 2, "vertical": "Financial services", "use_case_id": "anomaly-detection",
        "use_case": "Threat visibility", "technology_id": "cybersecurity-platform", "technology": "Cybersecurity Platform",
        "article_count": 14, "relevance": 82, "confidence": 76, "horizon": "Next",
        "horizon_reason": "concrete evidence exists but does not converge: only 1 of 2 distinct sources",
        "horizon_rule": "Concrete but not yet converging", "momentum": "+8%",
        "summary": "Banks are strengthening network-level visibility as operational resilience requirements move into execution.",
        "updated": "Today", "breakdown": [], "signal_mix": DEMO_SIGNAL_MIX, "orange_fit_score": 54,
        **_demo_horizon(2, 1, 5, 4), **_demo_gate(1, 2, 76),
    },
    {
        "id": 3, "vertical": "Public sector", "use_case_id": "document-processing-extraction",
        "use_case": "Trusted document processing", "technology_id": "generative-ai-llms", "technology": "Generative AI / LLMs",
        "article_count": 11, "relevance": 79, "confidence": 72, "horizon": "Next",
        "horizon_reason": "3 competitor/market signals within 180 days, no committed spend or deployment yet",
        "horizon_rule": "Forming market", "momentum": "+19%",
        "summary": "Public services are testing governed language systems for high-volume citizen and administrative workflows.",
        "updated": "Yesterday", "breakdown": [], "signal_mix": DEMO_SIGNAL_MIX, "orange_fit_score": 0,
        **_demo_horizon(0, 0, 3, 6), **_demo_gate(2, 3, 72),
    },
    {
        "id": 4, "vertical": "Energy & utilities", "use_case_id": "energy-optimization",
        "use_case": "Energy optimization", "technology_id": "edge-computing", "technology": "Edge Computing",
        "article_count": 9, "relevance": 74, "confidence": 68, "horizon": "Later",
        "horizon_reason": "evidenced only by tech_maturity - viability, not demand",
        "horizon_rule": "Not yet actionable", "momentum": "+6%",
        "summary": "Distributed control and local intelligence are emerging as grid flexibility becomes more valuable.",
        "updated": "2 days ago", "breakdown": [], "signal_mix": DEMO_SIGNAL_MIX, "orange_fit_score": 25,
        **_demo_horizon(0, 0, 0, 7), **_demo_gate(1, 1, 68),
    },
]

def _demo_signal(signal_type: str, days_ago: int, rationale: str, event_date: str = "") -> dict:
    """A demo signal shaped exactly like the classification rows the explanation
    fields read. Dates are relative so the placeholder never ages out of the
    recency window and starts claiming there is no recent signal."""
    return {
        "signal_type": signal_type,
        "signal_date": (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat(),
        "event_date": event_date or None,
        "event_date_precision": "exact" if event_date else "none",
        "signal_type_rationale": rationale,
    }


DEMO_SIGNALS = {
    1: [
        _demo_signal("buying_signal", 24, "Regional operator awarded a framework for connected maintenance across twelve plants."),
        _demo_signal("proof_signal", 61, "Producer reports 18% less unplanned downtime after a twelve-month rollout."),
    ],
    2: [
        _demo_signal("regulation", 40, "Operational resilience regime sets testing obligations for in-scope financial entities.", "2027-01-17"),
    ],
    3: [
        _demo_signal("competitor_move", 33, "Integrator launched a governed document assistant aimed at public administrations."),
        _demo_signal("market_trend", 88, "Public sector language model spending forecast to grow 28% annually in Europe."),
    ],
    4: [
        _demo_signal("tech_maturity", 120, "Edge inference cost per stream down roughly 45% with the new accelerator generation."),
    ],
}

# Placeholder countries per demo space, rolled up through the real index below.
# The fourth is deliberately empty: the "no geography at all" state has to be
# visible in the placeholder too, since it is the state the filter most needs to
# handle correctly and the one a demo would otherwise never show.
DEMO_COUNTRIES = {1: ["DE", "NL"], 2: ["GB"], 3: ["FR", "BE"], 4: []}

for _demo in DEMO_OPPORTUNITIES:
    # Derived through the same mapping tables the pipeline persists from, so the
    # placeholder can never show a domain the real derivation would not produce.
    _demo.update(_domain_fields(*domain_service.derive(_demo["technology_id"], _demo["use_case_id"])))
    _resolution = geography_service.INDEX.resolve(DEMO_COUNTRIES[_demo["id"]])
    _demo.update(_geography_fields(
        _resolution.regions[0] if _resolution.regions else "",
        list(_resolution.regions), list(_resolution.countries),
    ))
    _demo.update(_persona_fields(persona_service.derive(
        _demo["use_case_id"], _demo["primary_domain"], _demo["vertical"],
    )))
    # Composed through the live path, so the demo can never show an explanation
    # shape the real composition would not produce.
    _demo.update(explanation_service.compose(DEMO_SIGNALS[_demo["id"]], _demo))

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


_ARTICLE_BASE_COLUMNS = "a.id,a.source_name,a.source_type,a.extra,a.published_date,a.collected_at"
_CLASSIFICATION_COLUMNS = (
    "c.confidence,c.signal_type,c.signal_type_confidence,c.signal_date,"
    "c.event_date,c.event_date_precision,c.signal_type_rationale,c.signal_type_plain_summary"
)


def _articles_query(connection: sqlite3.Connection, tables: set[str]) -> str:
    """A database that hasn't run the classifier yet has no
    article_classifications table, and one written before the signal-type
    fields landed has the table but not the columns. Both are legitimate
    states, so the columns are requested only when they exist rather than
    letting the read fail."""
    if "article_classifications" not in tables:
        return f"SELECT {_ARTICLE_BASE_COLUMNS} FROM articles a"
    columns = {row[1] for row in connection.execute("PRAGMA table_info(article_classifications)")}
    selected = ",".join(
        column for column in _CLASSIFICATION_COLUMNS.split(",")
        if column.split(".", 1)[1] in columns
    )
    return (
        f"SELECT {_ARTICLE_BASE_COLUMNS}{',' + selected if selected else ''} "
        "FROM articles a LEFT JOIN article_classifications c ON c.article_id=a.id"
    )


def _space_domains(connection: sqlite3.Connection, tables: set[str]) -> dict[int, list[str]]:
    """Persisted domain membership per space, in derivation order (primary
    first). Absent for a database written before the join table existed - the
    caller falls back to deriving from the mapping tables."""
    if "opportunity_space_domains" not in tables:
        return {}
    grouped: dict[int, list[str]] = {}
    for space_id, domain_id in connection.execute(
        "SELECT space_id,domain_id FROM opportunity_space_domains ORDER BY space_id,ordinal"
    ):
        grouped.setdefault(space_id, []).append(domain_id)
    return grouped


def _space_personas(connection: sqlite3.Connection, tables: set[str]) -> dict[int, list[dict]]:
    """Persisted persona weights per space, strongest first. Absent for a
    database written before the join table existed - the caller falls back to
    deriving from the weight tables."""
    if "opportunity_space_personas" not in tables:
        return {}
    grouped: dict[int, list[dict]] = {}
    for space_id, persona_id, weight, source in connection.execute(
        "SELECT space_id,persona_id,weight,source FROM opportunity_space_personas "
        "ORDER BY space_id,weight DESC,persona_id"
    ):
        grouped.setdefault(space_id, []).append({
            "id": persona_id, "label": persona_service.label(persona_id),
            "weight": float(weight), "source": source,
        })
    return grouped


def _space_regions(connection: sqlite3.Connection, tables: set[str]) -> dict[int, list[str]]:
    """Persisted region membership per space, primary first. Absent for a
    database written before the join table existed - there is no derivation
    fallback for geography, so those spaces read as unspecified."""
    if "opportunity_space_regions" not in tables:
        return {}
    grouped: dict[int, list[str]] = {}
    for space_id, region_id in connection.execute(
        "SELECT space_id,region_id FROM opportunity_space_regions "
        "ORDER BY space_id,is_primary DESC,ordinal"
    ):
        grouped.setdefault(space_id, []).append(region_id)
    return grouped


def _opportunity_space_columns(connection: sqlite3.Connection) -> str:
    """primary_region and countries only exist after the geography backfill has
    added them, and a database that predates it is a legitimate state - so they
    are requested only when present rather than letting the read fail."""
    base = "id,vertical,use_case_id,technology_id,article_count,linked_article_ids,last_updated_at"
    existing = {row[1] for row in connection.execute("PRAGMA table_info(opportunity_spaces)")}
    return ",".join([base] + [c for c in ("primary_region", "countries") if c in existing])


def _geography_of(row: sqlite3.Row, region_ids: list[str] | None) -> tuple[str, list[str], list[str]]:
    """One space's persisted geography as (primary, regions, countries). An
    empty result is a real answer - a space no signal could place - so nothing
    is derived or guessed to fill it."""
    keys = row.keys()
    regions = list(region_ids or [])
    primary = (row["primary_region"] if "primary_region" in keys else None) or ""
    if not primary and regions:
        primary = regions[0]
    countries = json.loads(row["countries"] or "[]") if "countries" in keys and row["countries"] else []
    return primary, regions, countries


def list_opportunities() -> list[dict]:
    if not database_ready():
        return DEMO_OPPORTUNITIES
    with _connect() as connection:
        rows = connection.execute(
            f"SELECT {_opportunity_space_columns(connection)} FROM opportunity_spaces"
        ).fetchall()
        if not rows:
            return DEMO_OPPORTUNITIES
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        domains_by_space = _space_domains(connection, tables)
        personas_by_space = _space_personas(connection, tables)
        regions_by_space = _space_regions(connection, tables)
        articles_by_id = {
            row["id"]: dict(row)
            for row in connection.execute(_articles_query(connection, tables))
        }
        sources_by_name = (
            {row["source_name"]: dict(row) for row in connection.execute("SELECT source_name,category,audited_at FROM sources")}
            if "sources" in tables else {}
        )

    priorities = extension_store.orange_priorities()
    priority_use_cases = set(priorities["use_case_ids"])
    priority_technologies = set(priorities["technology_ids"])
    # Whether Orange has configured ANY priority at all - company-wide, not
    # per-space. Read by explanations.py's orange_fit_clause() so it only
    # phrases a space's Orange Fit score as a real priorities match when one
    # was actually possible; otherwise orange_fit_score is the domain-coverage
    # fallback (a weaker proxy), which reads differently on purpose.
    orange_priorities_configured = bool(priority_use_cases or priority_technologies)

    parsed = []
    for row in rows:
        linked_ids = json.loads(row["linked_article_ids"] or "[]")
        article_rows = [articles_by_id[aid] for aid in linked_ids if aid in articles_by_id]
        raw_market = attractiveness.market_signal_strength_raw(article_rows)
        source_cred = attractiveness.source_credibility(article_rows, sources_by_name)
        evid_qual = attractiveness.evidence_quality(article_rows, sources_by_name)
        raw_novelty, momentum_pct, momentum_is_new = attractiveness.novelty_momentum_raw(article_rows)
        verdict = horizon_service.compute(article_rows)
        parsed.append({
            "row": row, "raw_market": raw_market, "source_cred": source_cred,
            "evid_qual": evid_qual, "raw_novelty": raw_novelty, "momentum_pct": momentum_pct,
            "momentum_is_new": momentum_is_new,
            "verdict": verdict, "signal_mix": horizon_service.type_mix(article_rows),
            # Kept for the explanation fields, which need the individual signals
            # (type, dates, rationale) rather than the aggregated counts.
            "article_rows": article_rows,
        })

    market_scores = attractiveness.normalize_market_signal({item["row"]["id"]: item["raw_market"] for item in parsed})
    novelty_scores = attractiveness.normalize_novelty({item["row"]["id"]: item["raw_novelty"] for item in parsed})

    output = []
    for item in parsed:
        row = item["row"]
        components = {
            "market_signal_strength": market_scores.get(row["id"]),
            "source_credibility": item["source_cred"],
            "evidence_quality": item["evid_qual"],
            "novelty_momentum": novelty_scores.get(row["id"]),
        }
        score, _ = attractiveness.combine(components)
        breakdown = [{
            "key": key, "label": attractiveness.COMPONENT_LABELS[key],
            "value": round(value) if value is not None else 0,
            "weight": round(attractiveness.WEIGHTS[key] * 100),
            "available": value is not None,
        } for key, value in components.items()]

        momentum_pct = item["momentum_pct"]
        if item["momentum_is_new"]:
            momentum_display = "New"       # fresh evidence, nothing prior to compare against
        elif momentum_pct is not None:
            momentum_display = f"{momentum_pct:+.0f}%"
        else:
            momentum_display = "—"         # not enough dated evidence - unknown, not 0%

        confidence = round(item["evid_qual"]) if item["evid_qual"] is not None else 0
        verdict = item["verdict"]
        domain_ids = domains_by_space.get(row["id"])
        if domain_ids:
            primary_domain = domain_ids[0]
        else:
            primary_domain, domain_ids = domain_service.derive(row["technology_id"], row["use_case_id"])
        persona_weights = personas_by_space.get(row["id"])
        if persona_weights is None:
            persona_weights = persona_service.derive(
                row["use_case_id"], primary_domain, row["vertical"],
            )
        orange_fit_score = round(attractiveness.orange_fit(
            row["use_case_id"], row["technology_id"], priority_use_cases, priority_technologies, domain_ids,
        ))
        independent_sources = attractiveness.independent_source_count(item["article_rows"])
        independent_events = attractiveness.independent_event_count(item["article_rows"])
        space = {
            "id": row["id"], "vertical": row["vertical"], "use_case_id": row["use_case_id"],
            "use_case": USE_CASES.get(row["use_case_id"], row["use_case_id"].replace("-", " ").title()),
            "technology_id": row["technology_id"],
            "technology": TECHNOLOGIES.get(row["technology_id"], row["technology_id"].replace("-", " ").title()),
            **_domain_fields(primary_domain, domain_ids),
            **_persona_fields(persona_weights),
            **_geography_fields(*_geography_of(row, regions_by_space.get(row["id"]))),
            "article_count": row["article_count"], "relevance": score, "confidence": confidence,
            "horizon": verdict.horizon, "horizon_reason": verdict.reason,
            "horizon_rule": horizon_service.rule_label(verdict.rule),
            "horizon_breakdown": horizon_service.breakdown_rows(verdict),
            "signal_mix": item["signal_mix"],
            "momentum": momentum_display,
            "summary": f"{row['article_count']} institutional signals connect {USE_CASES.get(row['use_case_id'], row['use_case_id'])} with {TECHNOLOGIES.get(row['technology_id'], row['technology_id'])} in {row['vertical']}.",
            "updated": (row["last_updated_at"] or "Recently")[:10],
            "breakdown": breakdown,
            "orange_fit_score": orange_fit_score,
            "orange_priorities_configured": orange_priorities_configured,
            "publication_status": attractiveness.radar_watchlist_gate(independent_sources, independent_events, confidence),
            "gate_breakdown": attractiveness.gate_breakdown_rows(independent_sources, independent_events, confidence),
        }
        # Composed last: the three explanation fields read the domain, persona
        # and horizon values assembled above rather than re-deriving them.
        space.update(explanation_service.compose(item["article_rows"], space))
        output.append(space)
    output.sort(key=lambda item: (-item["relevance"], -item["article_count"]))
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


def pipeline_preflight() -> dict:
    """Preview the classifier work a run would do right now, without starting
    collection or API calls. No cap: a run always classifies the entire
    pending pool, so this reports that full count rather than one clipped to
    a user-chosen limit."""
    if not TEAM_DB.exists() or not database_ready():
        return {"articles": 0, "classification_calls": 0, "pool": 0, "ml_scored": 0, "spaces": 0}
    with _connect() as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        pool = connection.execute("SELECT COUNT(*) FROM classification_pool").fetchone()[0] if "classification_pool" in tables else 0
        classified = connection.execute("SELECT COUNT(*) FROM article_classifications").fetchone()[0] if "article_classifications" in tables else 0
        pending = max(pool - classified, 0)
        ml_scored = connection.execute("SELECT COUNT(*) FROM ml_noise_scores").fetchone()[0] if "ml_noise_scores" in tables else 0
        spaces = connection.execute("SELECT COUNT(*) FROM opportunity_spaces").fetchone()[0] if "opportunity_spaces" in tables else 0
    return {"articles": pending, "classification_calls": pending, "pool": pool, "ml_scored": ml_scored, "spaces": spaces}


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
