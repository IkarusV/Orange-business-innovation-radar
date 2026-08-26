"""Four-component Attractiveness score, replacing the old "Strategic fit"
proxy (which was either a rarely-populated LLM field or a raw article-count
ratio dressed up as a percentage - see docs/scoring_requirements_gap_analysis_2026-08-25.pdf).

Weights match the requirements deck (slide 17) minus strategic relevance,
each backed by a concrete, defensible calculation instead of an opinion:
    30% market signal strength   - recency-weighted density of linked evidence
    20% source credibility       - mean category-anchored trust score of sources
                                    (Pipelineteamfile/common/trust.py), falling
                                    back to a fixed source-type prior for a
                                    source the category audit hasn't reached yet
    20% evidence quality         - blend of mean per-article classifier
                                    confidence (an anchored rubric, see
                                    opportunity_classifier/config/prompt_template.txt)
                                    and an always-available evidence-count /
                                    source-independence component, so a space
                                    with no classifier confidence yet still
                                    gets a real number instead of "unavailable"
    15% novelty & momentum       - period-over-period growth in evidence dates, ranked
                                    against every other space's growth this run

Strategic relevance (match against Orange's own selected priority use
cases/technologies) is Orange Business fit / right-to-win, not a market
attractiveness input - it is scored separately by `orange_fit()` below and
never enters this weighted sum. `radar_watchlist_gate()` is a third,
independent output: a Radar/Watchlist publication gate on evidence
independence, ported from the team's Analysis/05_score_opportunities.py.

Every remaining component can legitimately be unavailable (no dated evidence
yet, no audited sources yet) - in that case it's excluded from the weighted
sum and the remaining weights are rescaled, rather than silently counting a
missing signal as a 0.

The Now/Next/Later time-horizon badge is NOT computed here and is not one of
the weighted components above (the deck's locked weights, minus strategic
relevance). It answers a different question - "how close is the thing that
makes this matter" - from signal types and dates, and it must not read
anything derived from this module. See radar_v2/services/horizon.py.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Optional

from radar_v2.constants import TEAM_PIPELINE

_TEAM_ROOT = str(TEAM_PIPELINE)
if _TEAM_ROOT not in sys.path:
    sys.path.insert(0, _TEAM_ROOT)

from common.trust import compute_trust  # noqa: E402  (needs the sys.path insert above)

MARKET_SIGNAL_HALF_LIFE_DAYS = 270  # ~9 months
NOVELTY_RECENT_WINDOW_DAYS = 90
NOVELTY_PRIOR_WINDOW_DAYS = 90

_BASE_WEIGHTS = {
    "market_signal_strength": 0.30,
    "source_credibility": 0.20,
    "evidence_quality": 0.20,
    "novelty_momentum": 0.15,
}
# Renormalized to sum to 1.0 now that strategic relevance (the deck's 5th,
# 15% component) has been pulled out into the standalone orange_fit() score
# below. combine() already rescales dynamically over whichever components are
# available for a given space, so this only fixes the displayed weight badges
# (30/20/20/15 used to read as "85% of 100" once the 5th component left) - it
# does not change combine()'s behavior when a component is unavailable.
_WEIGHT_SUM = sum(_BASE_WEIGHTS.values())
WEIGHTS = {key: value / _WEIGHT_SUM for key, value in _BASE_WEIGHTS.items()}

COMPONENT_LABELS = {
    "market_signal_strength": "Market signal strength",
    "source_credibility": "Source credibility",
    "evidence_quality": "Evidence quality",
    "novelty_momentum": "Novelty & momentum",
}

# Evidence-quality fallback weights (Analysis/05_score_opportunities.py's
# confidence_score, ported): always computable from article count, source
# independence and mean source trust, so a space with no classifier
# confidence yet still gets a real evidence-quality number.
EVIDENCE_COUNT_CAP = 5
EVIDENCE_SOURCE_CAP = 3
EVIDENCE_COUNT_WEIGHT = 35
EVIDENCE_SOURCE_WEIGHT = 30
EVIDENCE_TRUST_WEIGHT = 35
CLASSIFIER_COVERAGE_MIN = 0.5    # share of articles needing a classifier confidence to blend it in
CLASSIFIER_BLEND_WEIGHT = 0.7

# Orange Fit domain-coverage fallback, used only while no Orange priorities
# are configured yet.
ORANGE_FIT_DOMAIN_CAP = 4

# Radar/Watchlist publication gate (Analysis/05_score_opportunities.py's
# passes_radar_gate, ported): an explicit evidence-independence bar, separate
# from the Attractiveness score itself.
RADAR_MIN_INDEPENDENT_EVENTS = 2
RADAR_MIN_INDEPENDENT_SOURCES = 2
RADAR_MIN_CONFIDENCE = 45


def _parse_date(value: Optional[str]):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _age_days(date_value: Optional[str], now: datetime) -> Optional[float]:
    parsed = _parse_date(date_value)
    if parsed is None:
        return None
    return max((now - parsed).total_seconds() / 86400, 0.0)


def market_signal_strength_raw(article_rows: list[dict]) -> float:
    """Recency-weighted signal density: each linked article contributes a
    weight that halves every MARKET_SIGNAL_HALF_LIFE_DAYS. An article with no
    usable date gets a neutral half-weight rather than 0 (penalizing missing
    metadata) or 1 (rewarding it). Returns a raw sum - normalize across all
    spaces with normalize_market_signal() before using as a 0-100 score.
    """
    now = datetime.now(timezone.utc)
    total = 0.0
    for row in article_rows:
        age = _age_days(row.get("published_date") or row.get("collected_at"), now)
        weight = 0.5 if age is None else 0.5 ** (age / MARKET_SIGNAL_HALF_LIFE_DAYS)
        total += weight
    return total


def normalize_market_signal(raw_values: dict[int, float]) -> dict[int, float]:
    """Scale raw decayed-density sums to 0-100 against the strongest space in
    the current set, so the metric stays meaningful as the corpus grows."""
    peak = max(raw_values.values()) if raw_values else 0.0
    if peak <= 0:
        return {key: 50.0 for key in raw_values}  # no dated evidence anywhere yet - neutral, not 0
    return {key: min(value / peak, 1.0) * 100 for key, value in raw_values.items()}


def source_credibility(article_rows: list[dict], sources_by_name: dict[str, dict]) -> Optional[float]:
    """Mean trust score (0-100) of the sources behind this space's linked
    articles. A source with no category audit yet falls back to a fixed
    source-type prior (`common/trust.py`'s `SOURCE_TYPE_PRIORS`) rather than
    being dropped from the mean, so a space isn't scored on fewer sources than
    it actually has just because the auditor hasn't reached them. Returns None
    only when there are no article rows at all."""
    scores = []
    for row in article_rows:
        trust = compute_trust(sources_by_name.get(row.get("source_name")), source_type=row.get("source_type"))
        if trust.score is not None:
            scores.append(trust.score)
    return (sum(scores) / len(scores)) if scores else None


def independent_source_count(article_rows: list[dict]) -> int:
    """Distinct publishers behind this space's evidence - repeated coverage of
    the same outlet does not count twice."""
    return len({(row.get("source_name") or "").strip() or "Unknown source" for row in article_rows})


def independent_event_count(article_rows: list[dict]) -> int:
    """Distinct dated signals behind this space's evidence. Falls back to
    distinct article id when a row has no signal_date yet, so an article
    without a resolved signal type still counts as its own event rather than
    silently merging with every other undated row."""
    keys = set()
    for row in article_rows:
        keys.add(row.get("signal_date") or f"article:{row.get('id')}")
    return len(keys)


def evidence_quality(article_rows: list[dict], sources_by_name: dict[str, dict]) -> Optional[float]:
    """Evidence confidence, blending two sources:
      - classifier confidence: mean per-article classifier confidence (0-1,
        scaled to 0-100) - the strongest signal when it exists.
      - evidence-based: always-computable from article count, source
        independence and mean source trust (Analysis/05_score_opportunities.py's
        confidence_score, ported), so a space with no classifier confidence
        yet - e.g. a directly-imported space that never went through the paid
        classifier - still gets a real number instead of "unavailable".
    When classifier confidence covers at least half this space's articles, the
    two are blended 70/30 in the classifier's favor; otherwise the
    evidence-based component is used alone. Returns None only when there is no
    evidence at all.
    """
    if not article_rows:
        return None
    classifier_values = [row["confidence"] * 100 for row in article_rows if row.get("confidence") is not None]
    classifier_mean = (sum(classifier_values) / len(classifier_values)) if classifier_values else None
    coverage = len(classifier_values) / len(article_rows)

    trust = source_credibility(article_rows, sources_by_name)
    evidence_component = min(len(article_rows) / EVIDENCE_COUNT_CAP, 1) * EVIDENCE_COUNT_WEIGHT
    independence_component = min(independent_source_count(article_rows) / EVIDENCE_SOURCE_CAP, 1) * EVIDENCE_SOURCE_WEIGHT
    quality_component = min((trust or 0) / 100, 1) * EVIDENCE_TRUST_WEIGHT
    evidence_based = evidence_component + independence_component + quality_component

    if classifier_mean is None:
        return evidence_based
    if coverage >= CLASSIFIER_COVERAGE_MIN:
        return CLASSIFIER_BLEND_WEIGHT * classifier_mean + (1 - CLASSIFIER_BLEND_WEIGHT) * evidence_based
    return evidence_based


def novelty_momentum_raw(article_rows: list[dict]) -> tuple[Optional[float], Optional[float], bool]:
    """Per-space growth signal, plus human-readable context: articles dated in
    the last NOVELTY_RECENT_WINDOW_DAYS vs. the equal-length window before
    that. Returns (raw_growth, display_pct, is_new):
      - raw_growth: recent_count - prior_count, a signed magnitude. This is
        NOT a 0-100 score - normalize_novelty() ranks it against every other
        space computed in the same run before it's usable as one. A fixed
        curve (e.g. "1 article -> 2 articles = +100%, so score 100") was
        tried and rejected: most spaces on the radar carry only 1-2 articles
        total, so an absolute-percent curve is dominated by noise from tiny
        denominators. Ranking against what every other space did this run is
        robust to that - "New" and "+100%" mean less in isolation than they
        do relative to how much everyone else grew.
      - display_pct: the actual % change for showing as "+42%" in the UI, or
        None when there isn't enough dated evidence to compare (a genuinely
        unknown trend, not a bad one - never silently shown as 0%) OR when
        is_new is True (a % change is meaningless with nothing prior to compare).
      - is_new: True when there's fresh evidence but nothing in the prior
        window to compare against - "New" is the honest label, not a percent.
    """
    now = datetime.now(timezone.utc)
    recent = prior = 0
    for row in article_rows:
        age = _age_days(row.get("published_date") or row.get("collected_at"), now)
        if age is None:
            continue
        if age <= NOVELTY_RECENT_WINDOW_DAYS:
            recent += 1
        elif age <= NOVELTY_RECENT_WINDOW_DAYS + NOVELTY_PRIOR_WINDOW_DAYS:
            prior += 1
    if recent == 0 and prior == 0:
        return None, None, False
    if prior == 0:
        return float(recent), None, True  # all dated evidence is fresh, nothing older to compare - "New", not a percent
    display_pct = (recent - prior) / prior * 100
    return float(recent - prior), display_pct, False


def normalize_novelty(raw_values: dict[int, Optional[float]]) -> dict[int, Optional[float]]:
    """Percentile-rank each space's raw growth (recent_count - prior_count)
    against every other space in the current set: the fraction of peers with
    a strictly lower raw value, plus half credit for ties, scaled to 0-100.
    50 means this space's growth was exactly median for the run; it says
    nothing about whether growth is happening in absolute terms, only how
    this space compares to its peers right now. A space with no dated
    evidence stays None here too - excluded from the weighted sum, not
    ranked as median."""
    available = {key: value for key, value in raw_values.items() if value is not None}
    if not available:
        return {key: None for key in raw_values}
    sorted_values = sorted(available.values())
    n = len(sorted_values)

    def percentile(value: float) -> float:
        lower = sum(1 for v in sorted_values if v < value)
        equal = sum(1 for v in sorted_values if v == value)
        return (lower + equal / 2) / n * 100

    return {key: (percentile(value) if value is not None else None) for key, value in raw_values.items()}


def strategic_relevance(
    use_case_id: str, technology_id: str,
    priority_use_cases: set[str], priority_technologies: set[str],
) -> Optional[float]:
    """Explicit match against Orange's own selected priority use cases/
    technologies (set in the Company tab). None means Orange hasn't configured
    any priorities yet - an unset signal, not a zero score. This is the
    primary input to `orange_fit()` below, not to the Attractiveness score:
    Orange Business fit / right-to-win is a separate question from market
    attractiveness."""
    if not priority_use_cases and not priority_technologies:
        return None
    if priority_use_cases and priority_technologies:
        use_case_hit = use_case_id in priority_use_cases
        technology_hit = technology_id in priority_technologies
        if use_case_hit and technology_hit:
            return 100.0
        if use_case_hit or technology_hit:
            return 50.0
        return 0.0
    if priority_use_cases:
        return 100.0 if use_case_id in priority_use_cases else 0.0
    return 100.0 if technology_id in priority_technologies else 0.0


def orange_fit(
    use_case_id: str, technology_id: str,
    priority_use_cases: set[str], priority_technologies: set[str],
    domain_ids: list[str],
) -> float:
    """Orange Business fit / right-to-win, standalone from Attractiveness.
    Primary signal is the explicit priority match above; while Orange hasn't
    configured any priorities yet, falls back to how many distinct Orange
    Business domains (radar_v2/services/domains.py) this space touches, as a
    capability-alignment proxy - the taxonomy-driven equivalent of
    Analysis/04b_auto_enrich_candidates.py's ORANGE_CAPABILITY_TERMS keyword
    match, reusing the domain mapping this app already derives per space
    instead of a second free-text classifier. Unlike the explicit match, this
    fallback is always a number (0 domains is a real answer, not "unset")."""
    explicit = strategic_relevance(use_case_id, technology_id, priority_use_cases, priority_technologies)
    if explicit is not None:
        return explicit
    return min(len(domain_ids or []), ORANGE_FIT_DOMAIN_CAP) / ORANGE_FIT_DOMAIN_CAP * 100


def combine(components: dict[str, Optional[float]]) -> tuple[int, dict[str, Optional[float]]]:
    """Weighted sum over whichever components actually have a value; missing
    ones are excluded and the remaining weights rescaled, so a data gap never
    silently drags the score toward 0. Returns (rounded_score, raw_components)
    so the caller can both display the number and explain it."""
    available = {key: value for key, value in components.items() if value is not None}
    if not available:
        return 0, components
    weight_sum = sum(WEIGHTS[key] for key in available)
    score = sum(WEIGHTS[key] * value for key, value in available.items()) / weight_sum
    return round(score), components


def radar_watchlist_gate(independent_sources: int, independent_events: int, confidence: float) -> str:
    """Radar/Watchlist publication gate, ported from
    Analysis/05_score_opportunities.py's passes_radar_gate: independent of the
    Attractiveness score, this is purely about whether the evidence behind a
    space is diverse and confident enough to call it a curated Radar pick
    rather than a Watchlist item. Nothing is hidden by either outcome - this
    only decides which badge and filter chip a space carries."""
    passes = (
        independent_events >= RADAR_MIN_INDEPENDENT_EVENTS
        and independent_sources >= RADAR_MIN_INDEPENDENT_SOURCES
        and confidence >= RADAR_MIN_CONFIDENCE
    )
    return "RADAR" if passes else "WATCHLIST"


def gate_breakdown_rows(independent_sources: int, independent_events: int, confidence: float) -> list[dict]:
    """The "why Radar/Watchlist" panel: one row per gate condition, shaped like
    horizon.breakdown_rows() so the detail page can render both with the same
    component."""
    return [
        {
            "key": "independent_events", "label": "Independent events", "value": independent_events,
            "detail": f"Distinct dated signals, not the same story repeated. {RADAR_MIN_INDEPENDENT_EVENTS} needed for Radar.",
            "met": independent_events >= RADAR_MIN_INDEPENDENT_EVENTS,
        },
        {
            "key": "independent_sources", "label": "Independent sources", "value": independent_sources,
            "detail": f"Distinct publishers behind the evidence. {RADAR_MIN_INDEPENDENT_SOURCES} needed for Radar.",
            "met": independent_sources >= RADAR_MIN_INDEPENDENT_SOURCES,
        },
        {
            "key": "confidence", "label": "Evidence confidence", "value": round(confidence),
            "detail": f"Blended classifier and evidence-based confidence. {RADAR_MIN_CONFIDENCE} needed for Radar.",
            "met": confidence >= RADAR_MIN_CONFIDENCE,
        },
    ]
