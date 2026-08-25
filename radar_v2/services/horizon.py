"""App-side Now/Next/Later horizon: turns the signal-type rows the classifier
persisted into a badge plus the explanation behind it.

This replaces the old urgency_horizon(), which read a single nearest structured
deadline and could only ever see TED and CORDIS - every RSS-evidenced space
fell through to Later regardless of what the evidence actually said. Horizon is
now derived from what kind of signals a space has and when they landed.

The rules themselves live in Pipelineteamfile/common/signal_types.py so the
pipeline (which persists a horizon at recompute time) and the app (which shows
a live one) can never drift apart. This module only assembles rows and formats
the result for the UI.

INDEPENDENCE: nothing here reads the attractiveness score, the article count,
the recency-weighted volume proxy, or the classifier's taxonomy confidence.
The only inputs are signal types, signal dates, event dates, source names and
per-signal signal_type_confidence. tests/test_signal_horizon.py asserts it.
"""
from __future__ import annotations

import sys
from typing import Optional

from radar_v2.constants import TEAM_PIPELINE

_TEAM_ROOT = str(TEAM_PIPELINE)
if _TEAM_ROOT not in sys.path:
    sys.path.insert(0, _TEAM_ROOT)

from common.signal_types import (  # noqa: E402  (needs the sys.path insert above)
    DEFAULT_HORIZON_CONFIG,
    HorizonConfig,
    HorizonVerdict,
    LATER,
    NEXT,
    NOW,
    SIGNAL_TYPE_BY_SLUG,
    aggregate_horizon,
)

# Only the fields the horizon rules are allowed to see. Assembling the signal
# dict through this list is what keeps an unrelated column from silently
# becoming a horizon input later.
SIGNAL_FIELDS = (
    "source_name",
    "signal_type",
    "signal_type_confidence",
    "signal_date",
    "event_date",
    "event_date_precision",
)

RULE_LABELS = {
    "now_converging_evidence": "Converging concrete evidence",
    "next_concrete_but_below_now_bar": "Concrete but not yet converging",
    "next_forming_market": "Forming market",
    "later_default": "Not yet actionable",
}

SIGNAL_TYPE_LABELS = {
    "buying_signal": "Buying signal",
    "regulation": "Regulation",
    "proof_signal": "Proof signal",
    "competitor_move": "Competitor move",
    "market_trend": "Market trend",
    "tech_maturity": "Tech maturity",
}


def signals_from_rows(article_rows: list[dict]) -> list[dict]:
    """Project article/classification rows down to the horizon inputs only."""
    return [{field: row.get(field) for field in SIGNAL_FIELDS} for row in article_rows]


def compute(article_rows: list[dict], config: HorizonConfig = DEFAULT_HORIZON_CONFIG) -> HorizonVerdict:
    return aggregate_horizon(signals_from_rows(article_rows), config=config)


def breakdown_rows(verdict: HorizonVerdict, config: HorizonConfig = DEFAULT_HORIZON_CONFIG) -> list[dict]:
    """The "why this timing" panel: one row per horizon prior, plus the
    converging-sources check that separates Now from Next. Mirrors how the
    attractiveness breakdown explains its own number."""
    return [
        {
            "key": "now",
            "label": "Signals pointing at Now",
            "value": verdict.now_count,
            "detail": f"Committed spend or reported deployments. {config.now_min_signals} needed for a Now badge.",
            "met": verdict.now_count >= config.now_min_signals,
        },
        {
            "key": "sources",
            "label": "Distinct sources behind them",
            "value": verdict.distinct_sources,
            "detail": f"One source repeating itself is not convergence. {config.now_min_sources} needed for a Now badge.",
            "met": verdict.distinct_sources >= config.now_min_sources,
        },
        {
            "key": "next",
            "label": "Signals pointing at Next",
            "value": verdict.next_count,
            "detail": f"Competitor moves, market trends and regulation landing inside {config.regulation_next_months} months.",
            "met": verdict.next_count > 0,
        },
        {
            "key": "later",
            "label": "Signals pointing at Later",
            "value": verdict.later_count,
            "detail": "Research and technology maturing ahead of anyone buying it.",
            "met": verdict.later_count > 0,
        },
        {
            "key": "excluded",
            "label": "Not counted",
            "value": verdict.out_of_window_count + verdict.untyped_count,
            "detail": (
                f"{verdict.out_of_window_count} outside the {config.recency_window_days}-day window, "
                f"{verdict.untyped_count} with no signal type. These still count toward attractiveness."
            ),
            "met": (verdict.out_of_window_count + verdict.untyped_count) == 0,
        },
    ]


def type_mix(article_rows: list[dict]) -> list[dict]:
    """Counts per signal type across a space's evidence, for the detail page.
    Includes the distinguishing question so a reader can check the call."""
    counts: dict[str, int] = {}
    for signal in signals_from_rows(article_rows):
        slug = signal.get("signal_type")
        if slug in SIGNAL_TYPE_BY_SLUG:
            counts[slug] = counts.get(slug, 0) + 1
    return [
        {
            "key": slug,
            "label": SIGNAL_TYPE_LABELS.get(slug, slug),
            "value": count,
            "question": SIGNAL_TYPE_BY_SLUG[slug]["question"],
        }
        for slug, count in sorted(counts.items(), key=lambda item: -item[1])
    ]


def rule_label(rule: Optional[str]) -> str:
    return RULE_LABELS.get(rule or "", "Not yet actionable")


__all__ = [
    "LATER", "NEXT", "NOW", "SIGNAL_TYPE_LABELS",
    "breakdown_rows", "compute", "rule_label", "signals_from_rows", "type_mix",
]
