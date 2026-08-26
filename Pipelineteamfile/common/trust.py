"""Category-anchored source trust scoring: each source is assigned exactly one
publisher-type category. The score comes mechanically from a fixed anchor
table for that category - never from a per-outlet judgment call. Anchors live
here as the single source of truth, so retuning a weight never requires
re-auditing any source (the score is recomputed from the stored category on
every read, never stored itself).

Ported from the reference implementation in the sibling `Pipeline Opportunity`
project - see that project's `common/trust.py` for the original design notes
(a prior NewsGuard-style 9-criterion checklist was tried and scrapped because
it forced primary-source government feeds to score 0).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

# "primary_source_institutional" is never LLM-assigned (auto_assignable=False) -
# it is reserved for this pipeline's own hardcoded government/EU data feeds
# (see HARDCODED_SOURCES below), so a 100 score can only ever come from that
# explicit hardcoding, never from an automated category guess.
CATEGORIES = [
    {"slug": "primary_source_institutional", "anchor": 100, "auto_assignable": False,
     "description": "This pipeline's own primary government/EU data feed (not news about it) - hardcoded only"},
    {"slug": "peer_reviewed_journal", "anchor": 95, "auto_assignable": True,
     "description": "Peer-reviewed academic journal"},
    {"slug": "wire_service", "anchor": 90, "auto_assignable": True,
     "description": "Wire service (e.g. Reuters, AP, AFP)"},
    {"slug": "major_national_financial_press", "anchor": 80, "auto_assignable": True,
     "description": "Major national or financial press with editorial staff (e.g. WSJ, NYT, FT, Bloomberg)"},
    {"slug": "government_official_body", "anchor": 75, "auto_assignable": True,
     "description": "Government or official body publishing about itself - authoritative but not neutral on itself"},
    {"slug": "specialized_trade_press", "anchor": 65, "auto_assignable": True,
     "description": "Specialized trade press with editorial staff (an industry-vertical trade publication)"},
    {"slug": "think_tank_consultancy", "anchor": 55, "auto_assignable": True,
     "description": "Think tank or consultancy (e.g. Brookings, BCG, McKinsey)"},
    {"slug": "corporate_newsroom_pr", "anchor": 35, "auto_assignable": True,
     "description": "Corporate newsroom, PR, or owned media - the outlet is itself the subject of its own coverage"},
    {"slug": "aggregator_unknown", "anchor": 20, "auto_assignable": True,
     "description": "Aggregator, or a publisher type not confidently recognized - the safe default"},
]
ANCHOR_BY_SLUG = {c["slug"]: c["anchor"] for c in CATEGORIES}
CATEGORY_SLUGS = [c["slug"] for c in CATEGORIES]
AUTO_ASSIGNABLE_SLUGS = [c["slug"] for c in CATEGORIES if c["auto_assignable"]]
DEFAULT_UNKNOWN_CATEGORY = "aggregator_unknown"

# This pipeline's own institutional collectors, not news publishers reporting
# on them - government-approved primary sources, trusted outright. Matches
# the exact source_name strings written by ted_collector, cordis_collector
# and ocds_collector (see their collector/fetch.py).
HARDCODED_SOURCES = {
    "TED": "primary_source_institutional",
    "CORDIS": "primary_source_institutional",
    "UK Find a Tender": "primary_source_institutional",
    "UK Contracts Finder": "primary_source_institutional",
    "Ukraine ProZorro": "primary_source_institutional",
}

HIGH_TRUST_MIN = 75
TRUSTED_MIN = 60
STALE_AFTER_DAYS = 365  # ~12 months

# Fallback for a source with no category audit yet: a fixed prior by feed
# type rather than dropping it from every trust-weighted average entirely.
# Ported from the team's Analysis/04_enrich_candidates.py SOURCE_PRIORS table
# (feature/alec-scoring) - same institutional-feeds-trusted-more ordering as
# the category anchors above, just coarser. Only ever used when the per-outlet
# category audit hasn't reached this source yet; an audited source's score is
# never overridden by its type prior.
SOURCE_TYPE_PRIORS = {
    "ted": 90,
    "ocds_uk": 90,
    "ocds_ua": 90,
    "cordis": 80,
    "rss": 55,
    "gnews": 45,
}
DEFAULT_SOURCE_TYPE_PRIOR = 30


@dataclass
class TrustResult:
    score: Optional[float]   # None when unaudited and no source_type prior applies
    status: str              # unaudited | type_prior | high_trust | trusted | fail
    category: Optional[str]
    stale: bool


def is_stale(audited_at: Optional[str]) -> bool:
    if not audited_at:
        return False
    audited = datetime.fromisoformat(audited_at)
    if audited.tzinfo is None:
        audited = audited.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - audited > timedelta(days=STALE_AFTER_DAYS)


def compute_trust(source_row: Optional[dict], source_type: Optional[str] = None) -> TrustResult:
    """source_row: mapping with 'category' and 'audited_at' (e.g. a sqlite3.Row
    from the `sources` table). A missing audited_at or an unrecognized category
    slug are treated as unaudited - never guessed.

    When the source is unaudited and `source_type` is given, falls back to
    `SOURCE_TYPE_PRIORS` (status="type_prior") instead of returning no score at
    all. Callers that don't pass `source_type` (existing audit tooling) keep
    the original unaudited-is-None behavior unchanged.
    """
    if source_row is None or source_row["audited_at"] is None or source_row["category"] is None:
        if source_type is not None:
            prior = SOURCE_TYPE_PRIORS.get(source_type, DEFAULT_SOURCE_TYPE_PRIOR)
            return TrustResult(score=float(prior), status="type_prior", category=None, stale=False)
        return TrustResult(score=None, status="unaudited", category=None, stale=False)

    category = source_row["category"]
    anchor = ANCHOR_BY_SLUG.get(category)
    if anchor is None:
        if source_type is not None:
            prior = SOURCE_TYPE_PRIORS.get(source_type, DEFAULT_SOURCE_TYPE_PRIOR)
            return TrustResult(score=float(prior), status="type_prior", category=category, stale=False)
        return TrustResult(score=None, status="unaudited", category=category, stale=False)

    if anchor >= HIGH_TRUST_MIN:
        status = "high_trust"
    elif anchor >= TRUSTED_MIN:
        status = "trusted"
    else:
        status = "fail"

    return TrustResult(score=float(anchor), status=status, category=category,
                        stale=is_stale(source_row["audited_at"]))
