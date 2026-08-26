import json
import sqlite3
from datetime import datetime
from typing import Optional

from common.business_domains import DomainIndex, coverage_report
from common.geography import (
    GeographyIndex,
    aggregate_geography,
    coverage_report as geography_coverage_report,
)
from common.personas import PersonaIndex, coverage_report as persona_coverage_report
from common.signal_types import aggregate_horizon

from . import taxonomy as taxonomy_mod

SCHEMA = """
CREATE TABLE IF NOT EXISTS article_classifications (
    article_id INTEGER PRIMARY KEY,
    use_case_id TEXT,
    technology_id TEXT,
    confidence REAL,
    evidence TEXT,
    status TEXT NOT NULL,
    client_relevance REAL,
    client_relevance_reason TEXT,
    client_context_ref TEXT,
    tokens_used INTEGER,
    classified_at TEXT NOT NULL,
    FOREIGN KEY (article_id) REFERENCES articles(id)
);
CREATE INDEX IF NOT EXISTS idx_classifications_status ON article_classifications(status);

CREATE TABLE IF NOT EXISTS opportunity_spaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical TEXT NOT NULL,
    use_case_id TEXT NOT NULL,
    technology_id TEXT NOT NULL,
    article_count INTEGER NOT NULL,
    avg_client_relevance REAL,
    linked_article_ids TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    UNIQUE(vertical, use_case_id, technology_id)
);

-- Business domains are multi-valued per space, so they live in a join table
-- rather than a delimited column: one row per space x domain, indexed on
-- domain_id so a multi-select filter stays a query rather than a scan.
-- Every row is derived from taxonomy.json and is safe to drop and rebuild.
CREATE TABLE IF NOT EXISTS opportunity_space_domains (
    space_id INTEGER NOT NULL,
    domain_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    is_primary INTEGER NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (space_id, domain_id),
    FOREIGN KEY (space_id) REFERENCES opportunity_spaces(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_space_domains_domain ON opportunity_space_domains(domain_id);

-- Target personas are multi-valued AND weighted per space, so the weight is
-- persisted rather than recomputed at render time: multi-select filtering at a
-- threshold and persona-weighted sorting both push down into the query.
-- Only non-zero weights are stored - an absent row is 0.0, and a suppressed
-- pair is deleted rather than written as an explicit zero.
CREATE TABLE IF NOT EXISTS opportunity_space_personas (
    space_id INTEGER NOT NULL,
    persona_id TEXT NOT NULL,
    weight REAL NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (space_id, persona_id),
    FOREIGN KEY (space_id) REFERENCES opportunity_spaces(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_space_personas_persona
    ON opportunity_space_personas(persona_id, weight);

-- Regions are multi-valued per space, so the same join-table shape as domains,
-- indexed on region_id so a multi-select geography filter stays a query rather
-- than a scan. signal_count is the number of qualifying signals that put the
-- space in this region - it is what chose primary_region, kept so the choice
-- stays auditable instead of only being re-derivable.
CREATE TABLE IF NOT EXISTS opportunity_space_regions (
    space_id INTEGER NOT NULL,
    region_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    is_primary INTEGER NOT NULL,
    signal_count INTEGER NOT NULL,
    latest_signal_date TEXT,
    PRIMARY KEY (space_id, region_id),
    FOREIGN KEY (space_id) REFERENCES opportunity_spaces(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_space_regions_region ON opportunity_space_regions(region_id);
"""

# Added after the original schema shipped, so applied as ALTERs rather than
# folded into SCHEMA above - existing databases carry real classified rows.
CLASSIFICATION_COLUMNS = {
    "tokens_used": "INTEGER",
    "signal_type": "TEXT",
    "signal_type_confidence": "REAL",
    "signal_date": "TEXT",
    "event_date": "TEXT",
    "event_date_precision": "TEXT",
    "signal_type_rationale": "TEXT",
    # Same fact as signal_type_rationale, in plain language for a non-technical
    # reader - radar_v2/services/explanations.py's hot_now_clause() prefers
    # this when present, falling back to a truncation of the rationale above
    # for any row this hasn't been backfilled onto yet.
    "signal_type_plain_summary": "TEXT",
    "signal_type_assigned_by": "TEXT",
    # Geography, per signal. countries/regions/unresolved_countries are JSON
    # arrays because a signal is legitimately multi-country (a CORDIS consortium
    # project) and a delimited column would need parsing anyway. The filter
    # queries the space-level join table, never these.
    "countries": "TEXT",
    "regions": "TEXT",
    "region_override": "TEXT",
    "geography_confidence": "REAL",
    "geography_assigned_by": "TEXT",
    "unresolved_countries": "TEXT",
}

# The horizon verdict is persisted next to the space so the badge is auditable
# from the pipeline side, not only re-derivable in the app.
SPACE_COLUMNS = {
    "horizon": "TEXT",
    "horizon_rule": "TEXT",
    "horizon_reason": "TEXT",
    "horizon_now_count": "INTEGER",
    "horizon_next_count": "INTEGER",
    "horizon_later_count": "INTEGER",
    "horizon_distinct_sources": "INTEGER",
    "horizon_gated_count": "INTEGER",
    "horizon_out_of_window_count": "INTEGER",
    "horizon_untyped_count": "INTEGER",
    "horizon_computed_at": "TEXT",
    # Single-value display (badges, quadrant colouring). The full set lives in
    # opportunity_space_domains; this is always its first entry.
    "primary_domain": "TEXT",
    # Geography, resolved and indexed rather than computed at render time. NULL
    # primary_region means no geography on any qualifying signal - a valid state
    # that displays as "Global / unspecified", and deliberately NOT the same as
    # a space whose regions include the explicit `global` tag.
    "primary_region": "TEXT",
    "countries": "TEXT",
    "geography_unresolved": "TEXT",
    "geography_tagged_signals": "INTEGER",
    "geography_untagged_signals": "INTEGER",
    "geography_out_of_window_signals": "INTEGER",
    "geography_low_confidence_signals": "INTEGER",
    "geography_computed_at": "TEXT",
}


def _add_missing_columns(conn: sqlite3.Connection, table: str, columns: dict) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, column_type in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _add_missing_columns(conn, "article_classifications", CLASSIFICATION_COLUMNS)
    _add_missing_columns(conn, "opportunity_spaces", SPACE_COLUMNS)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_classifications_signal_type ON article_classifications(signal_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_spaces_primary_region ON opportunity_spaces(primary_region)")
    conn.commit()


def already_classified_ids(conn: sqlite3.Connection) -> set:
    return {row[0] for row in conn.execute("SELECT article_id FROM article_classifications")}


def already_typed_ids(conn: sqlite3.Connection) -> set:
    """Articles that already carry a valid signal type. Kept separate from
    already_classified_ids so a rerun after the signal-type fields landed can
    top up the rows that predate them without re-spending on the rest."""
    return {
        row[0] for row in conn.execute(
            "SELECT article_id FROM article_classifications WHERE signal_type IS NOT NULL"
        )
    }


def _json_list(value) -> Optional[str]:
    """A list field as stored JSON. An empty list is stored as '[]', not NULL:
    "the model looked and found no country" and "geography was never run on this
    row" have to stay distinguishable."""
    return json.dumps(list(value)) if value is not None else None


def upsert_classification(
    conn: sqlite3.Connection,
    article_id: int,
    result,
    client_context_ref: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO article_classifications
            (article_id, use_case_id, technology_id, confidence, evidence, status,
             client_relevance, client_relevance_reason, client_context_ref, tokens_used, classified_at,
             signal_type, signal_type_confidence, signal_date, event_date, event_date_precision,
             signal_type_rationale, signal_type_plain_summary, signal_type_assigned_by,
             countries, regions, region_override, geography_confidence,
             geography_assigned_by, unresolved_countries)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            article_id,
            result.use_case_id,
            result.technology_id,
            result.confidence,
            result.evidence,
            result.status,
            result.client_relevance,
            result.client_relevance_reason,
            client_context_ref,
            result.total_tokens,
            datetime.utcnow().isoformat(),
            result.signal_type,
            result.signal_type_confidence,
            result.signal_date,
            result.event_date,
            result.event_date_precision,
            result.signal_type_rationale,
            result.signal_type_plain_summary,
            result.signal_type_assigned_by,
            _json_list(result.countries),
            _json_list(result.regions),
            result.region_override,
            result.geography_confidence,
            result.geography_assigned_by,
            _json_list(result.unresolved_countries),
        ),
    )


def update_geography(
    conn: sqlite3.Connection,
    article_id: int,
    resolution,
    assigned_by: Optional[str] = None,
    tokens: int = 0,
) -> None:
    """Write only the geography fields onto an existing classification row. Used
    both by the deterministic pass (which costs nothing) and by the LLM backfill
    for RSS rows - in neither case is the taxonomy or signal-type result the row
    already carries touched or re-spent on."""
    conn.execute(
        """
        UPDATE article_classifications
        SET countries = ?, regions = ?, region_override = ?, geography_confidence = ?,
            geography_assigned_by = ?, unresolved_countries = ?,
            tokens_used = COALESCE(tokens_used, 0) + ?
        WHERE article_id = ?
        """,
        (
            _json_list(resolution.countries),
            _json_list(resolution.regions),
            resolution.region_override or None,
            resolution.confidence,
            assigned_by or resolution.assigned_by,
            _json_list(resolution.unresolved),
            tokens,
            article_id,
        ),
    )


def already_geotagged_ids(conn: sqlite3.Connection) -> set:
    """Articles whose classification row has been through geography resolution.
    Keyed on `regions` rather than on a non-empty country list, because an empty
    result is a real answer - re-running those would re-spend on rows that are
    already correct."""
    return {
        row[0] for row in conn.execute(
            "SELECT article_id FROM article_classifications WHERE regions IS NOT NULL"
        )
    }


def update_plain_summary(conn: sqlite3.Connection, article_id: int, plain_summary: str, tokens: int = 0) -> None:
    """Write only signal_type_plain_summary onto an existing classification
    row. Used by the plain-summary backfill for rows classified before this
    field existed - the signal_type, rationale and every taxonomy field the
    row already carries are untouched and not re-spent on."""
    conn.execute(
        """
        UPDATE article_classifications
        SET signal_type_plain_summary = ?, tokens_used = COALESCE(tokens_used, 0) + ?
        WHERE article_id = ?
        """,
        (plain_summary, tokens, article_id),
    )


def update_signal_type(conn: sqlite3.Connection, article_id: int, result) -> None:
    """Write only the signal-type fields onto an existing classification row.
    Used when an article was classified before these fields existed - the
    taxonomy result it already has is untouched and not re-spent on."""
    conn.execute(
        """
        UPDATE article_classifications
        SET signal_type = ?, signal_type_confidence = ?, signal_date = ?, event_date = ?,
            event_date_precision = ?, signal_type_rationale = ?, signal_type_plain_summary = ?,
            signal_type_assigned_by = ?, tokens_used = COALESCE(tokens_used, 0) + ?
        WHERE article_id = ?
        """,
        (
            result.signal_type, result.signal_type_confidence, result.signal_date,
            result.event_date, result.event_date_precision, result.signal_type_rationale,
            result.signal_type_plain_summary,
            result.signal_type_assigned_by, result.total_tokens, article_id,
        ),
    )


def space_signals(conn: sqlite3.Connection) -> dict:
    """Signal rows per (vertical, use_case_id, technology_id), carrying only
    what the horizon rules are allowed to read: type, dates, source identity
    and per-signal confidence. Deliberately no article counts, no
    classification confidence, no client relevance - horizon must not be a
    restatement of attractiveness."""
    rows = conn.execute(
        """
        SELECT a.vertical, c.use_case_id, c.technology_id, a.source_name,
               c.signal_type, c.signal_type_confidence, c.signal_date,
               c.event_date, c.event_date_precision
        FROM article_classifications c
        JOIN articles a ON a.id = c.article_id
        WHERE c.status = 'classified'
          AND c.use_case_id IS NOT NULL
          AND c.technology_id IS NOT NULL
        """
    ).fetchall()
    grouped = {}
    for vertical, use_case_id, technology_id, source_name, signal_type, signal_confidence, signal_date, event_date, precision in rows:
        grouped.setdefault((vertical, use_case_id, technology_id), []).append({
            "source_name": source_name,
            "signal_type": signal_type,
            "signal_type_confidence": signal_confidence,
            "signal_date": signal_date,
            "event_date": event_date,
            "event_date_precision": precision,
        })
    return grouped


def _load_json_list(value) -> list:
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    return loaded if isinstance(loaded, list) else []


def space_geography_signals(conn: sqlite3.Connection) -> dict:
    """Geography rows per (vertical, use_case_id, technology_id), carrying only
    what the aggregation is allowed to read: resolved countries and regions, the
    explicit override, the signal date for the recency window, and the
    per-signal confidence for the flag. Deliberately no article counts and no
    attractiveness input - geography is a filter dimension, not a score."""
    rows = conn.execute(
        """
        SELECT a.vertical, c.use_case_id, c.technology_id,
               c.countries, c.regions, c.region_override, c.geography_confidence,
               c.unresolved_countries, c.signal_date, a.published_date
        FROM article_classifications c
        JOIN articles a ON a.id = c.article_id
        WHERE c.status = 'classified'
          AND c.use_case_id IS NOT NULL
          AND c.technology_id IS NOT NULL
        """
    ).fetchall()
    grouped = {}
    for (vertical, use_case_id, technology_id, countries, regions, override,
         confidence, unresolved, signal_date, published_date) in rows:
        grouped.setdefault((vertical, use_case_id, technology_id), []).append({
            "countries": _load_json_list(countries),
            "regions": _load_json_list(regions),
            "region_override": override,
            "geography_confidence": confidence,
            "unresolved": _load_json_list(unresolved),
            "signal_date": signal_date or published_date,
        })
    return grouped


def write_space_regions(conn: sqlite3.Connection, space_id: int, verdict) -> None:
    """Replace one space's region rows with the currently aggregated set.
    Idempotent by construction - the previous rows are dropped first, so a rerun
    after a taxonomy correction leaves no stale membership behind."""
    conn.execute("DELETE FROM opportunity_space_regions WHERE space_id=?", (space_id,))
    conn.executemany(
        "INSERT INTO opportunity_space_regions "
        "(space_id, region_id, ordinal, is_primary, signal_count, latest_signal_date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (space_id, region_id, ordinal, 1 if region_id == verdict.primary_region else 0,
             verdict.region_counts.get(region_id, 0), verdict.region_latest.get(region_id))
            for ordinal, region_id in enumerate(verdict.regions)
        ],
    )


def write_space_geography(conn: sqlite3.Connection, space_id: int, verdict, computed_at: str) -> None:
    """The resolved geography onto the space row plus its region join rows."""
    conn.execute(
        """
        UPDATE opportunity_spaces
        SET primary_region = ?, countries = ?, geography_unresolved = ?,
            geography_tagged_signals = ?, geography_untagged_signals = ?,
            geography_out_of_window_signals = ?, geography_low_confidence_signals = ?,
            geography_computed_at = ?
        WHERE id = ?
        """,
        (
            verdict.primary_region or None,
            json.dumps(list(verdict.countries)),
            json.dumps(list(verdict.unresolved)),
            verdict.tagged_signals,
            verdict.untagged_signals,
            verdict.out_of_window_signals,
            verdict.low_confidence_signals,
            computed_at,
            space_id,
        ),
    )
    write_space_regions(conn, space_id, verdict)


def recompute_opportunity_spaces(conn: sqlite3.Connection) -> int:
    """Recompute all opportunity_spaces from current article_classifications.
    Idempotent: upserts on (vertical, use_case_id, technology_id), preserving
    first_seen_at across reruns.
    """
    rows = conn.execute(
        """
        SELECT a.vertical, c.use_case_id, c.technology_id, c.article_id, c.client_relevance
        FROM article_classifications c
        JOIN articles a ON a.id = c.article_id
        WHERE c.status = 'classified'
          AND c.use_case_id IS NOT NULL
          AND c.technology_id IS NOT NULL
        """
    ).fetchall()

    spaces = {}
    for vertical, use_case_id, technology_id, article_id, client_relevance in rows:
        key = (vertical, use_case_id, technology_id)
        bucket = spaces.setdefault(key, {"article_ids": [], "relevances": []})
        bucket["article_ids"].append(article_id)
        if client_relevance is not None:
            bucket["relevances"].append(client_relevance)

    signals_by_space = space_signals(conn) if spaces else {}
    geography_by_space = space_geography_signals(conn) if spaces else {}

    index = domain_index()
    personas = persona_index()
    regions = geography_index()

    now = datetime.utcnow().isoformat()
    current_keys = set(spaces)
    existing = {
        (row[1], row[2], row[3]): row[0]
        for row in conn.execute("SELECT id, vertical, use_case_id, technology_id FROM opportunity_spaces")
    }
    for stale_key in set(existing) - current_keys:
        conn.execute("DELETE FROM opportunity_space_domains WHERE space_id=?", (existing[stale_key],))
        conn.execute("DELETE FROM opportunity_space_personas WHERE space_id=?", (existing[stale_key],))
        conn.execute("DELETE FROM opportunity_space_regions WHERE space_id=?", (existing[stale_key],))
        conn.execute(
            "DELETE FROM opportunity_spaces WHERE vertical=? AND use_case_id=? AND technology_id=?",
            stale_key,
        )
    for (vertical, use_case_id, technology_id), bucket in spaces.items():
        article_ids = sorted(bucket["article_ids"])
        avg_relevance = (
            sum(bucket["relevances"]) / len(bucket["relevances"]) if bucket["relevances"] else None
        )
        verdict = aggregate_horizon(signals_by_space.get((vertical, use_case_id, technology_id), []))
        horizon = verdict.as_row()
        resolution = index.resolve(technology_id, use_case_id)
        conn.execute(
            """
            INSERT INTO opportunity_spaces
                (vertical, use_case_id, technology_id, article_count, avg_client_relevance,
                 linked_article_ids, first_seen_at, last_updated_at,
                 horizon, horizon_rule, horizon_reason, horizon_now_count, horizon_next_count,
                 horizon_later_count, horizon_distinct_sources, horizon_gated_count,
                 horizon_out_of_window_count, horizon_untyped_count, horizon_computed_at,
                 primary_domain)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(vertical, use_case_id, technology_id) DO UPDATE SET
                article_count = excluded.article_count,
                avg_client_relevance = excluded.avg_client_relevance,
                linked_article_ids = excluded.linked_article_ids,
                last_updated_at = excluded.last_updated_at,
                horizon = excluded.horizon,
                horizon_rule = excluded.horizon_rule,
                horizon_reason = excluded.horizon_reason,
                horizon_now_count = excluded.horizon_now_count,
                horizon_next_count = excluded.horizon_next_count,
                horizon_later_count = excluded.horizon_later_count,
                horizon_distinct_sources = excluded.horizon_distinct_sources,
                horizon_gated_count = excluded.horizon_gated_count,
                horizon_out_of_window_count = excluded.horizon_out_of_window_count,
                horizon_untyped_count = excluded.horizon_untyped_count,
                horizon_computed_at = excluded.horizon_computed_at,
                primary_domain = excluded.primary_domain
            """,
            (
                vertical, use_case_id, technology_id, len(article_ids), avg_relevance,
                json.dumps(article_ids), now, now,
                horizon["horizon"], horizon["horizon_rule"], horizon["horizon_reason"],
                horizon["horizon_now_count"], horizon["horizon_next_count"], horizon["horizon_later_count"],
                horizon["horizon_distinct_sources"], horizon["horizon_gated_count"],
                horizon["horizon_out_of_window_count"], horizon["horizon_untyped_count"], now,
                resolution.primary,
            ),
        )
        space_id = conn.execute(
            "SELECT id FROM opportunity_spaces WHERE vertical=? AND use_case_id=? AND technology_id=?",
            (vertical, use_case_id, technology_id),
        ).fetchone()[0]
        write_space_domains(conn, space_id, resolution)
        write_space_personas(
            conn, space_id, personas.resolve(use_case_id, resolution.primary, vertical)
        )
        write_space_geography(
            conn, space_id,
            aggregate_geography(
                regions, geography_by_space.get((vertical, use_case_id, technology_id), [])
            ),
            now,
        )
    conn.commit()
    return len(spaces)


def domain_index() -> DomainIndex:
    """Read the mapping tables fresh from taxonomy.json on every recompute, so
    a correction there is picked up without a restart and the persisted rows
    can never quietly outlive the configuration that produced them."""
    return taxonomy_mod.domain_index()


def write_space_domains(conn: sqlite3.Connection, space_id: int, resolution) -> None:
    """Replace one space's domain rows with the currently derived set.
    Idempotent by construction - the previous rows are dropped first, so a
    rerun after a mapping correction leaves no stale membership behind."""
    conn.execute("DELETE FROM opportunity_space_domains WHERE space_id=?", (space_id,))
    conn.executemany(
        "INSERT INTO opportunity_space_domains (space_id, domain_id, ordinal, is_primary, source) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (space_id, domain_id, ordinal, 1 if domain_id == resolution.primary else 0,
             resolution.source_of(domain_id))
            for ordinal, domain_id in enumerate(resolution.domains)
        ],
    )


def backfill_business_domains(conn: sqlite3.Connection) -> dict:
    """Derive business domains for every existing opportunity space from its
    current technology and use case assignment. Pure derivation from
    taxonomy.json - no LLM calls, no reclassification. Safe to re-run after any
    correction to the mapping tables."""
    ensure_schema(conn)
    index = domain_index()
    rows = conn.execute(
        "SELECT id, use_case_id, technology_id FROM opportunity_spaces"
    ).fetchall()
    resolutions = []
    for space_id, use_case_id, technology_id in rows:
        resolution = index.resolve(technology_id, use_case_id)
        conn.execute(
            "UPDATE opportunity_spaces SET primary_domain=? WHERE id=?",
            (resolution.primary, space_id),
        )
        write_space_domains(conn, space_id, resolution)
        resolutions.append(resolution)
    conn.execute(
        "DELETE FROM opportunity_space_domains WHERE space_id NOT IN (SELECT id FROM opportunity_spaces)"
    )
    conn.commit()
    return coverage_report(index, resolutions)


def domain_coverage(conn: sqlite3.Connection) -> dict:
    """The Part 6 numbers without writing anything - the same report the
    backfill returns, recomputed from the stored assignments."""
    index = domain_index()
    resolutions = [
        index.resolve(technology_id, use_case_id)
        for _space_id, use_case_id, technology_id in conn.execute(
            "SELECT id, use_case_id, technology_id FROM opportunity_spaces"
        )
    ]
    return coverage_report(index, resolutions)


def persona_index() -> PersonaIndex:
    """Read the persona tables fresh from taxonomy.json on every recompute, for
    the same reason as domain_index() - persisted weights must never quietly
    outlive the configuration that produced them."""
    return taxonomy_mod.persona_index()


def _space_persona_inputs(conn: sqlite3.Connection) -> list:
    """The three columns persona derivation reads. primary_domain may be NULL on
    a database that predates the domain backfill; it is derived on the fly there
    so the persona pass never depends on backfill ordering."""
    domains = None
    rows = []
    for space_id, vertical, use_case_id, technology_id, primary_domain in conn.execute(
        "SELECT id, vertical, use_case_id, technology_id, primary_domain FROM opportunity_spaces"
    ):
        if not primary_domain:
            domains = domains or domain_index()
            primary_domain = domains.resolve(technology_id, use_case_id).primary
        rows.append((space_id, vertical, use_case_id, primary_domain))
    return rows


def write_space_personas(conn: sqlite3.Connection, space_id: int, resolution) -> None:
    """Replace one space's persona rows with the currently derived weights.
    Idempotent by construction - previous rows are dropped first, so a rerun
    after a table or suppression correction leaves no stale weight behind."""
    conn.execute("DELETE FROM opportunity_space_personas WHERE space_id=?", (space_id,))
    conn.executemany(
        "INSERT INTO opportunity_space_personas (space_id, persona_id, weight, source) "
        "VALUES (?, ?, ?, ?)",
        [
            (space_id, entry.persona, entry.weight, entry.source)
            for entry in resolution.weights
            if entry.weight > 0
        ],
    )


def backfill_target_personas(conn: sqlite3.Connection) -> dict:
    """Derive target persona weights for every existing opportunity space from
    its current use case, primary domain and vertical. Pure derivation from
    taxonomy.json - no LLM calls, no reclassification. Safe to re-run after any
    correction to the weight tables or the suppression list."""
    ensure_schema(conn)
    index = persona_index()
    resolutions = []
    for space_id, vertical, use_case_id, primary_domain in _space_persona_inputs(conn):
        resolution = index.resolve(use_case_id, primary_domain, vertical)
        write_space_personas(conn, space_id, resolution)
        resolutions.append(resolution)
    conn.execute(
        "DELETE FROM opportunity_space_personas "
        "WHERE space_id NOT IN (SELECT id FROM opportunity_spaces)"
    )
    conn.commit()
    return persona_coverage_report(index, resolutions)


def persona_coverage(conn: sqlite3.Connection) -> dict:
    """The Part 9 numbers without writing anything - the same report the
    backfill returns, recomputed from the stored assignments."""
    index = persona_index()
    resolutions = [
        index.resolve(use_case_id, primary_domain, vertical)
        for _space_id, vertical, use_case_id, primary_domain in _space_persona_inputs(conn)
    ]
    return persona_coverage_report(index, resolutions)


def geography_index() -> GeographyIndex:
    """Read the region vocabulary fresh from taxonomy.json on every recompute,
    for the same reason as domain_index() - a country added to eastern-europe
    must take effect on the next backfill, not on the next restart."""
    return taxonomy_mod.geography_index()


def _space_geography_verdicts(conn: sqlite3.Connection, index: GeographyIndex) -> list:
    """(space id, verdict) pairs recomputed from the stored per-signal
    geography. The single place both the backfill and the report read from, so
    the numbers a report prints are always the numbers a backfill would write."""
    signals = space_geography_signals(conn)
    return [
        (
            space_id,
            aggregate_geography(index, signals.get((vertical, use_case_id, technology_id), [])),
        )
        for space_id, vertical, use_case_id, technology_id in conn.execute(
            "SELECT id, vertical, use_case_id, technology_id FROM opportunity_spaces"
        )
    ]


def backfill_geography(conn: sqlite3.Connection) -> dict:
    """Aggregate geography onto every existing opportunity space from the
    per-signal countries already resolved on its articles. Pure aggregation - no
    LLM calls and no re-extraction, so it is safe to re-run after any correction
    to the region tables. Populating the per-signal geography itself is a
    separate pass (backfill_signal_geography in main.py)."""
    ensure_schema(conn)
    index = geography_index()
    now = datetime.utcnow().isoformat()
    verdicts = _space_geography_verdicts(conn, index)
    for space_id, verdict in verdicts:
        write_space_geography(conn, space_id, verdict, now)
    conn.execute(
        "DELETE FROM opportunity_space_regions WHERE space_id NOT IN (SELECT id FROM opportunity_spaces)"
    )
    conn.commit()
    return geography_coverage_report(index, [verdict for _space_id, verdict in verdicts])


def geography_coverage(conn: sqlite3.Connection) -> dict:
    """The Part 6.5 numbers without writing anything - the same report the
    backfill returns, recomputed from the stored per-signal geography."""
    index = geography_index()
    return geography_coverage_report(
        index, [verdict for _space_id, verdict in _space_geography_verdicts(conn, index)]
    )


def geography_confidence_report(conn: sqlite3.Connection) -> dict:
    """Part 6.4: the share of inferred (RSS/GNews) signals below the confidence
    gate, and how the empty-array / global / country outcomes actually split.
    Deterministic sources are counted separately - they have no inference to be
    unconfident about, so folding them in would dilute the number the prompt is
    meant to be judged on."""
    rows = conn.execute(
        "SELECT a.source_type, c.geography_assigned_by, c.geography_confidence, "
        "       c.countries, c.region_override "
        "FROM article_classifications c JOIN articles a ON a.id = c.article_id "
        "WHERE c.regions IS NOT NULL"
    ).fetchall()
    by_assignment: dict = {}
    for source_type, assigned_by, confidence, countries, override in rows:
        bucket = by_assignment.setdefault(assigned_by or "unknown", {
            "signals": 0, "low_confidence": 0, "low_confidence_tagged": 0,
            "empty_countries": 0, "global_override": 0, "with_countries": 0,
            "source_types": {},
        })
        bucket["signals"] += 1
        bucket["source_types"][source_type] = bucket["source_types"].get(source_type, 0) + 1
        codes = _load_json_list(countries)
        tagged = bool(codes or override)
        if confidence is not None and confidence < 0.5:
            bucket["low_confidence"] += 1
            if tagged:
                # The number that actually judges the prompt: geography that was
                # asserted but weakly. A deliberate 0.0 on an empty array is the
                # prompt working, not failing, so it is counted separately.
                bucket["low_confidence_tagged"] += 1
        if codes:
            bucket["with_countries"] += 1
        else:
            bucket["empty_countries"] += 1
        if override:
            bucket["global_override"] += 1
    for bucket in by_assignment.values():
        bucket["low_confidence_share"] = (
            bucket["low_confidence"] / bucket["signals"] if bucket["signals"] else 0.0
        )
        tagged_total = bucket["with_countries"] + bucket["global_override"]
        bucket["low_confidence_tagged_share"] = (
            bucket["low_confidence_tagged"] / tagged_total if tagged_total else 0.0
        )
    return by_assignment


def persona_derivations(conn: sqlite3.Connection, limit: Optional[int] = None) -> list:
    """(space row, resolution) pairs for auditing the derivation by hand -
    Part 9.4's spot check, and the source of the suppression list in 9.3."""
    index = persona_index()
    rows = _space_persona_inputs(conn)
    if limit is not None:
        rows = rows[:limit]
    return [
        {
            "space_id": space_id, "vertical": vertical, "use_case_id": use_case_id,
            "primary_domain": primary_domain,
            "resolution": index.resolve(use_case_id, primary_domain, vertical),
        }
        for space_id, vertical, use_case_id, primary_domain in rows
    ]
