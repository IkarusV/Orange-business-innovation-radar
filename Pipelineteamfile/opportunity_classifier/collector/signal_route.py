"""Per-source routing for signal-type assignment: which articles get a
mechanically-derived signal type and which have to go through the LLM.

Three of the institutional sources are structurally one signal type - a TED
notice, an OCDS release and a SAM.gov notice are, by definition of the feed
they come from, a named body committing money. Sending them to the classifier
would only add cost and a chance of getting a certainty wrong. CORDIS is
mechanical too, but on the project's own status field rather than on the feed
identity. Everything else (RSS) needs the model.

Nothing here is guessed. A deterministic type is only returned when the source
type is one this module actually knows the shape of; anything else returns
None and the caller sends it to the LLM.
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from common.signal_types import parse_date

# Feed identity alone fixes the type for these. sam_gov has no collector in
# this repo yet - the mapping is here so a SAM.gov collector would route
# correctly the day it lands, not because anything currently produces it.
BUYING_SIGNAL_SOURCE_TYPES = {"ted", "ocds_uk", "ocds_ua", "sam_gov"}
DETERMINISTIC_SOURCE_TYPES = BUYING_SIGNAL_SOURCE_TYPES | {"cordis"}

BUYING_SIGNAL_CONFIDENCE = 1.0
CORDIS_CONFIDENCE = 0.9

# CORDIS renders dates as '31 {{month_03}} 2027' in search results - an
# unresolved i18n placeholder, not a month name, so no date library can touch
# it. Mirrors cordis_collector.fetch._parse_cordis_date.
_CORDIS_MONTH_PLACEHOLDER = re.compile(r"\{\{month_(\d{2})\}\}")


@dataclass
class SignalTypeAssignment:
    signal_type: str
    signal_type_confidence: float
    signal_date: Optional[str]
    event_date: Optional[str]
    event_date_precision: str
    signal_type_rationale: str
    assigned_by: str  # deterministic | llm


def parse_cordis_placeholder_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    match = _CORDIS_MONTH_PLACEHOLDER.search(raw)
    if not match:
        return parse_date(raw)  # the per-project JSON view returns a plain ISO date
    parts = _CORDIS_MONTH_PLACEHOLDER.sub(match.group(1), raw).split()
    if len(parts) != 3:
        return None
    try:
        day, month, year = (int(p) for p in parts)
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_ted_deadline(raw) -> Optional[datetime]:
    """TED's extra.deadline is a list of ISO datetime strings - one notice can
    carry a deadline per lot, and the earliest is the one that actually forces
    a decision."""
    if not raw:
        return None
    values = raw if isinstance(raw, (list, tuple)) else [raw]
    dates = [d for d in (parse_date(v) for v in values) if d is not None]
    return min(dates) if dates else None


def load_extra(extra) -> dict:
    if isinstance(extra, dict):
        return extra
    if isinstance(extra, str):
        try:
            loaded = json.loads(extra)
        except (json.JSONDecodeError, TypeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.date().isoformat() if value else None


def route(
    source_type: Optional[str],
    extra=None,
    published_date: Optional[str] = None,
    collected_at: Optional[str] = None,
    cordis_status: Optional[dict] = None,
) -> Optional[SignalTypeAssignment]:
    """Deterministic signal type for a known institutional source, or None when
    the article has to go to the LLM.

    cordis_status is the {"status", "result_count", "end_date"} payload from
    cordis_collector.fetch.fetch_project_status, or whatever was cached into
    the article's extra by a previous run. Without it a CORDIS project cannot
    be routed - returning None (LLM) is the honest answer rather than deriving
    a status from end_date < today, which would conflate "scheduled to end"
    with "actually closed and reported".
    """
    extra = load_extra(extra)
    signal_date = _iso(parse_date(published_date) or parse_date(collected_at))

    if source_type in BUYING_SIGNAL_SOURCE_TYPES:
        event_date, precision, note = _procurement_event_date(source_type, extra)
        return SignalTypeAssignment(
            signal_type="buying_signal",
            signal_type_confidence=BUYING_SIGNAL_CONFIDENCE,
            signal_date=signal_date,
            event_date=event_date,
            event_date_precision=precision,
            signal_type_rationale=f"{source_type} publishes only procurement notices - a named body committing money{note}",
            assigned_by="deterministic",
        )

    if source_type == "cordis":
        status_payload = cordis_status or extra.get("project_status_lookup")
        if not isinstance(status_payload, dict) or not status_payload.get("status"):
            return None
        status = str(status_payload["status"]).upper()
        result_count = int(status_payload.get("result_count") or 0)
        end_date = _iso(parse_cordis_placeholder_date(status_payload.get("end_date") or extra.get("end_date")))
        if status == "CLOSED" and result_count > 0:
            signal_type = "proof_signal"
            rationale = f"CORDIS project closed with {result_count} published results"
        elif status == "CLOSED":
            # Ended, but nothing published to point at - there is no measurable
            # reported result, so this is not proof of anything yet.
            signal_type = "tech_maturity"
            rationale = "CORDIS project closed with no published results"
        elif status == "TERMINATED":
            signal_type = "tech_maturity"
            rationale = "CORDIS project terminated - funded research, no reported outcome"
        else:  # SIGNED - signed and/or running; CORDIS has no separate ONGOING value
            signal_type = "tech_maturity"
            rationale = f"CORDIS project status {status} - funded research still running"
        return SignalTypeAssignment(
            signal_type=signal_type,
            signal_type_confidence=CORDIS_CONFIDENCE,
            signal_date=signal_date,
            event_date=end_date,
            event_date_precision="exact" if end_date else "none",
            signal_type_rationale=rationale,
            assigned_by="deterministic",
        )

    return None


def _procurement_event_date(source_type: str, extra: dict) -> tuple:
    """The date that makes a procurement signal time-bound. Only TED actually
    publishes one in what this pipeline collects: ted_collector requests the
    `deadline` field, so extra.deadline holds the tender close date(s). The
    OCDS collectors capture buyer, value, stage and CPV but no tenderPeriod
    end date, so a UK or Ukraine release has no usable close date today - it
    gets precision "none" rather than a fabricated one.
    """
    if source_type == "ted":
        deadline = parse_ted_deadline(extra.get("deadline"))
        if deadline:
            return _iso(deadline), "exact", f", closing {deadline.date().isoformat()}"
    return None, "none", ""


def cordis_status_for(conn, article_id: int, extra: dict, fetcher) -> Optional[dict]:
    """Look up (and cache into articles.extra) one CORDIS project's status.
    Cached so a rerun never re-fetches a project already resolved - the same
    skip-what's-done principle as already_classified_ids.
    """
    cached = extra.get("project_status_lookup")
    if isinstance(cached, dict) and cached.get("status"):
        return cached
    project_id = extra.get("reference") or extra.get("rcn")
    payload = fetcher(str(project_id)) if project_id else None
    if not payload or not payload.get("status"):
        return None
    extra["project_status_lookup"] = payload
    conn.execute("UPDATE articles SET extra = ? WHERE id = ?", (json.dumps(extra), article_id))
    return payload
