"""Five-component Attractiveness score, replacing the old "Strategic fit"
proxy (which was either a rarely-populated LLM field or a raw article-count
ratio dressed up as a percentage - see docs/scoring_requirements_gap_analysis_2026-08-25.pdf).

Weights match the requirements deck (slide 17), each backed by a concrete,
defensible calculation instead of an opinion:
    30% market signal strength   - recency-weighted density of linked evidence
    20% source credibility       - mean category-anchored trust score of sources
                                    (Pipelineteamfile/common/trust.py)
    20% evidence quality         - mean per-article classifier confidence, now
                                    under an anchored rubric (see
                                    opportunity_classifier/config/prompt_template.txt)
    15% novelty & momentum       - period-over-period growth in evidence dates, ranked
                                    against every other space's growth this run
    15% strategic relevance      - match against Orange's own selected priority
                                    use cases/technologies (Company tab)

Every component can legitimately be unavailable (no dated evidence yet, no
audited sources yet, no Orange priorities configured yet) - in that case it's
excluded from the weighted sum and the remaining weights are rescaled, rather
than silently counting a missing signal as a 0.

The Now/Next/Later time-horizon badge is NOT computed here and is not one of
the 5 weighted components above (the deck's 30/20/20/15/15 weights are locked).
It answers a different question - "how close is the thing that makes this
matter" - from signal types and dates, and it must not read anything derived
from this module. See radar_v2/services/horizon.py.
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

WEIGHTS = {
    "market_signal_strength": 0.30,
    "source_credibility": 0.20,
    "evidence_quality": 0.20,
    "novelty_momentum": 0.15,
    "strategic_relevance": 0.15,
}

COMPONENT_LABELS = {
    "market_signal_strength": "Market signal strength",
    "source_credibility": "Source credibility",
    "evidence_quality": "Evidence quality",
    "novelty_momentum": "Novelty & momentum",
    "strategic_relevance": "Strategic relevance",
}


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
    articles. Unaudited sources are excluded from the mean (not counted as 0)
    so a space isn't penalized just for evidence the auditor hasn't reached
    yet. Returns None if nothing here is audited."""
    scores = []
    for row in article_rows:
        trust = compute_trust(sources_by_name.get(row.get("source_name")))
        if trust.score is not None:
            scores.append(trust.score)
    return (sum(scores) / len(scores)) if scores else None


def evidence_quality(article_rows: list[dict]) -> Optional[float]:
    """Mean per-article classifier confidence (0-1, scaled to 0-100)."""
    values = [row["confidence"] * 100 for row in article_rows if row.get("confidence") is not None]
    return (sum(values) / len(values)) if values else None


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
    """Match against Orange's own selected priority use cases/technologies
    (set in the Company tab). None means Orange hasn't configured any
    priorities yet - an unset signal, not a zero score."""
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
