"""Per-source routing for geography: which articles carry their country in the
record and which have to have it inferred from free text.

Same shape as signal_route.py, and the same principle - nothing here is guessed.
TED, OCDS and SAM.gov publish the country as a field; CORDIS publishes a whole
participant list. For those four, geography is extraction plus normalisation and
the LLM is never involved. Everything else (RSS, and GNews if it were ever
collected) returns None and goes to the classifier, where geography is genuinely
an inference from text.

Field names below were confirmed against live data rather than taken from a
spec, because three of the four differ from what a reader would assume:
    TED       extra.buyer_country is a per-lot ARRAY of ISO alpha-3 codes
              (observed: ["SWE"]), not a single alpha-2 code.
    OCDS      extra.buyer_country is hardcoded "GB" / "UA" by the collector -
              each feed is single-country by construction.
    CORDIS    the search API returns no participant countries at all. They come
              from the per-project JSON view, whose `organization` associations
              carry address.country - the same call that already supplies the
              project status, so this costs no extra request.
    SAM.gov   has no collector in this repo. The branch exists so a collector
              would route correctly the day it lands; nothing produces it today.
"""
import json
from dataclasses import dataclass
from typing import Optional

from common.geography import DETERMINISTIC, GeographyIndex

from .signal_route import load_extra

# Feed identity or a single record field fixes the country for these.
DETERMINISTIC_SOURCE_TYPES = {"ted", "ocds_uk", "ocds_ua", "sam_gov", "cordis"}

# A field read off the record is a fact about the record, not a judgment.
DETERMINISTIC_CONFIDENCE = 1.0

# CORDIS's coordinator country is an English name in the search payload, used
# only when the per-project participant lookup is unavailable. It is one country
# where the participant list is several, so it is a floor, not an equivalent.
CORDIS_COORDINATOR_CONFIDENCE = 0.8

# SAM.gov place-of-performance and awardee country field names are unverified -
# no collector exists here to check them against a live response. Both spellings
# the OCDS-style and the SAM-style collectors would plausibly use are read, and
# the absence of all of them is reported rather than defaulted to "US".
SAM_COUNTRY_KEYS = (
    "place_of_performance_country", "pop_country", "awardee_country", "buyer_country",
)


@dataclass
class GeographyAssignment:
    """One article's mechanically-extracted geography, before the rollup."""
    countries: tuple
    source_field: str
    confidence: float
    assigned_by: str = DETERMINISTIC


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [item for item in value if item]
    return [value]


def extract_countries(source_type: Optional[str], extra, cordis_status=None) -> Optional[GeographyAssignment]:
    """Raw country tokens for a structured-source article, or None when the
    article has to go to the LLM. Tokens are returned in whatever shape the
    source emits (alpha-2, alpha-3, EU code, English name) - normalisation is
    common.geography's job, so a source-shape surprise surfaces there once
    rather than in four places."""
    extra = load_extra(extra)

    if source_type == "ted":
        codes = _as_list(extra.get("buyer_country"))
        return GeographyAssignment(tuple(codes), "extra.buyer_country", DETERMINISTIC_CONFIDENCE) if codes else None

    if source_type in ("ocds_uk", "ocds_ua"):
        codes = _as_list(extra.get("buyer_country"))
        return GeographyAssignment(tuple(codes), "extra.buyer_country", DETERMINISTIC_CONFIDENCE) if codes else None

    if source_type == "sam_gov":
        for key in SAM_COUNTRY_KEYS:
            codes = _as_list(extra.get(key))
            if codes:
                return GeographyAssignment(tuple(codes), f"extra.{key}", DETERMINISTIC_CONFIDENCE)
        return None

    if source_type == "cordis":
        payload = cordis_status or extra.get("project_status_lookup") or {}
        participants = _as_list(payload.get("participant_countries")) if isinstance(payload, dict) else []
        if participants:
            return GeographyAssignment(
                tuple(participants), "project.organization.address.country", DETERMINISTIC_CONFIDENCE
            )
        coordinator = extra.get("coordinated_in")
        if coordinator:
            # One country instead of the consortium's several. Better than no
            # geography, and honestly reported as the weaker source it is.
            return GeographyAssignment(
                (coordinator,), "extra.coordinated_in", CORDIS_COORDINATOR_CONFIDENCE
            )
        return None

    return None


def resolve(
    index: GeographyIndex,
    source_type: Optional[str],
    extra,
    cordis_status=None,
):
    """Extraction plus rollup for a structured-source article, or None when the
    article has to go to the LLM."""
    assignment = extract_countries(source_type, extra, cordis_status)
    if assignment is None:
        return None
    return index.resolve(
        assignment.countries,
        confidence=assignment.confidence,
        assigned_by=assignment.assigned_by,
    ), assignment


def cordis_participants_for(conn, article_id: int, extra: dict, fetcher) -> Optional[dict]:
    """Look up (and cache into articles.extra) one CORDIS project's participant
    countries, reusing the status lookup's cache entry and its single request.

    A payload cached by a run that predates participant countries carries a
    status but no country list, so the presence of the key - not of the payload -
    is what decides whether to re-fetch. The refreshed payload keeps the status
    fields, so signal-type routing reads exactly what it read before.
    """
    cached = extra.get("project_status_lookup")
    if isinstance(cached, dict) and "participant_countries" in cached:
        return cached
    project_id = extra.get("reference") or extra.get("rcn")
    payload = fetcher(str(project_id)) if project_id else None
    if not payload:
        return cached if isinstance(cached, dict) else None
    if isinstance(cached, dict):
        payload = {**cached, **payload}
    extra["project_status_lookup"] = payload
    conn.execute("UPDATE articles SET extra = ? WHERE id = ?", (json.dumps(extra), article_id))
    return payload


__all__ = [
    "CORDIS_COORDINATOR_CONFIDENCE", "DETERMINISTIC_CONFIDENCE", "DETERMINISTIC_SOURCE_TYPES",
    "SAM_COUNTRY_KEYS", "GeographyAssignment", "cordis_participants_for", "extract_countries",
    "resolve",
]
