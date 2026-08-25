"""App-side target personas: the eight buyer personas as a weighted, filterable
and rankable dimension on every opportunity space.

The vocabulary, both weight tables and the suppression list live in
Pipelineteamfile/opportunity_classifier/config/taxonomy.json and the derivation
and ranking rules in Pipelineteamfile/common/personas.py, so the pipeline
(which derives and persists) and the app (which reads, filters and ranks) can
never drift apart. Nothing here hardcodes a persona or a weight.

Reads normally come from the persisted opportunity_space_personas join table.
Derivation is only used as a fallback for a database written before that table
existed, so the portfolio still renders instead of showing an empty dimension.
"""
from __future__ import annotations

import json
import sys

from radar_v2.constants import TAXONOMY, TEAM_PIPELINE

_TEAM_ROOT = str(TEAM_PIPELINE)
if _TEAM_ROOT not in sys.path:
    sys.path.insert(0, _TEAM_ROOT)

from common.personas import (  # noqa: E402  (needs the sys.path insert above)
    DEFAULT_WEIGHT_THRESHOLD,
    PERSONA_SCORE_FLOOR,
    PERSONA_SCORE_SCALE,
    PersonaIndex,
    adjusted_score,
    build_index,
)


def _index() -> PersonaIndex:
    return build_index(json.loads(TAXONOMY.read_text(encoding="utf-8")))


INDEX = _index()
PERSONA_IDS = INDEX.ids
PERSONA_LABELS = INDEX.labels
_LABEL_TO_ID = {label: persona_id for persona_id, label in PERSONA_LABELS.items()}


def options() -> list[dict]:
    """Filter/picker options in taxonomy order - the deck's own persona
    ordering. This is what a persona dropdown renders from."""
    return INDEX.options()


def label(persona_id: str) -> str:
    return INDEX.label(persona_id)


def id_for_label(persona_label: str) -> str:
    """Reverse lookup for the picker, which - like every other filter select in
    this app - stores the display label as its value rather than a slug. Empty
    string for an unrecognised label, consistent with "" meaning no constraint
    everywhere else in this module."""
    return _LABEL_TO_ID.get(persona_label, "")


def derive(use_case_id: str | None, primary_domain: str | None, vertical: str | None) -> list[dict]:
    """Fallback derivation for spaces with no persisted persona rows. Tolerant
    where the pipeline is strict: an assignment outside the closed taxonomy
    yields no personas rather than breaking the page - the pipeline backfill is
    where that data error is meant to surface."""
    try:
        resolution = INDEX.resolve(use_case_id, primary_domain, vertical)
    except Exception:
        return []
    return [
        {"id": entry.persona, "label": INDEX.label(entry.persona),
         "weight": entry.weight, "source": entry.source}
        for entry in resolution.weights if entry.weight > 0
    ]


def weight_of(item: dict, persona_id: str) -> float:
    """A space's weight for one persona, 0.0 when absent or suppressed. Reads
    the persona_weights rows team_repository attaches to every opportunity."""
    if not persona_id:
        return 0.0
    for entry in item.get("persona_weights") or []:
        if entry["id"] == persona_id:
            return float(entry["weight"])
    return 0.0


def source_of(item: dict, persona_id: str) -> str:
    """Which table produced the weight - use_case, domain or both. Drives the
    explainability badge, the same principle as the horizon reason."""
    for entry in item.get("persona_weights") or []:
        if entry["id"] == persona_id:
            return str(entry["source"])
    return ""


def passes(item: dict, persona_id: str, threshold: float = DEFAULT_WEIGHT_THRESHOLD) -> bool:
    """Filter predicate: does this space clear the active weight threshold for
    this persona. An empty persona id is no constraint, so a filter nobody set
    never empties the list."""
    if not persona_id:
        return True
    return weight_of(item, persona_id) >= threshold


def passes_any(item: dict, persona_ids: list[str], threshold: float = DEFAULT_WEIGHT_THRESHOLD) -> bool:
    """OR within the persona dimension, per the multi-select filter semantics.
    Combining across dimensions stays the caller's AND."""
    if not persona_ids:
        return True
    return any(passes(item, persona_id, threshold) for persona_id in persona_ids)


def persona_adjusted_score(item: dict, persona_id: str) -> float:
    """The space's attractiveness score under the dampened persona multiplier.
    With no persona selected the base score is returned unadjusted - persona
    ranking is only meaningful once a persona is actually chosen."""
    base = float(item.get("relevance", 0) or 0)
    if not persona_id:
        return base
    return adjusted_score(base, weight_of(item, persona_id))


def sort_by_persona(items: list[dict], persona_id: str) -> list[dict]:
    """Rank by persona-adjusted score, keeping article count as the tie-breaker
    so ordering matches what team_repository produces for equal scores."""
    return sorted(
        items,
        key=lambda item: (-persona_adjusted_score(item, persona_id), -item.get("article_count", 0)),
    )


__all__ = [
    "DEFAULT_WEIGHT_THRESHOLD", "INDEX", "PERSONA_IDS", "PERSONA_LABELS",
    "PERSONA_SCORE_FLOOR", "PERSONA_SCORE_SCALE",
    "adjusted_score", "derive", "id_for_label", "label", "options", "passes", "passes_any",
    "persona_adjusted_score", "sort_by_persona", "source_of", "weight_of",
]
