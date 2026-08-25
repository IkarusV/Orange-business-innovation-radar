"""App-side geography: regions as a multi-valued, filterable dimension on every
opportunity space.

The region vocabulary and its country membership live in
Pipelineteamfile/opportunity_classifier/config/taxonomy.json and the rollup and
aggregation rules in Pipelineteamfile/common/geography.py, so the pipeline
(which resolves and persists) and the app (which reads and filters) can never
drift apart. Nothing here hardcodes a region or a country.

Reads come from the persisted opportunity_space_regions join table. There is no
derivation fallback, unlike domains and personas: geography is extracted from
signals rather than derived from a space's taxonomy assignment, so a database
without the join table has no geography to reconstruct. Those spaces render as
UNSPECIFIED_LABEL, which is the same, correct answer as a space whose signals
genuinely carried no country.

"Tagged global" and "untagged" are kept as separate states throughout. Filtering
on `global` returns only spaces explicitly resolved there - EU-wide regulation
and worldwide statements - and never the far larger set of spaces that simply
have no geography. Whether the two should look different in the UI once both are
on screen is a business call, not an engineering one; the data supports either.
"""
from __future__ import annotations

import json
import sys

from radar_v2.constants import TAXONOMY, TEAM_PIPELINE

_TEAM_ROOT = str(TEAM_PIPELINE)
if _TEAM_ROOT not in sys.path:
    sys.path.insert(0, _TEAM_ROOT)

from common.geography import (  # noqa: E402  (needs the sys.path insert above)
    CONFIDENCE_GATE,
    GLOBAL_REGION,
    GeographyIndex,
    build_index,
)

# What a space with no geography on any qualifying signal shows. Deliberately
# not the label of the `global` region: a space nobody could place is not the
# same as a space placed everywhere.
UNSPECIFIED_LABEL = "Global / unspecified"


def _index() -> GeographyIndex:
    return build_index(json.loads(TAXONOMY.read_text(encoding="utf-8")))


INDEX = _index()
REGION_IDS = INDEX.ids
REGION_LABELS = INDEX.labels


def options() -> list[dict]:
    """Filter options in taxonomy order - the business's own region ordering,
    near-Europe first and the rest of the world coarse behind it."""
    return INDEX.options()


def label(region_id: str) -> str:
    return INDEX.label(region_id)


def labels(region_ids: list[str]) -> list[str]:
    return [INDEX.label(region_id) for region_id in region_ids]


def primary_label(primary_region: str) -> str:
    """Single-value display: the badge, the radar visualisation. Falls back to
    the unspecified label rather than an empty string, so a space with no
    geography still reads as a deliberate state instead of a missing value."""
    return INDEX.label(primary_region) if primary_region else UNSPECIFIED_LABEL


def country_labels(country_codes: list[str]) -> list[str]:
    """ISO codes as-is. The app shows codes rather than names: the detail panel
    lists them next to a region label that already carries the meaning, and a
    name table would be a second vocabulary to keep in step with the first."""
    return [str(code).upper() for code in country_codes or []]


def passes_any(item: dict, region_ids: list[str]) -> bool:
    """OR within the geography dimension, per the multi-select filter semantics.
    Combining across dimensions stays the caller's AND. A space matches a
    selected region if it appears anywhere in its set, not only as primary."""
    if not region_ids:
        return True
    return bool(set(region_ids) & set(item.get("regions") or []))


def is_tagged_global(item: dict) -> bool:
    """Explicitly resolved to global - EU-wide regulation, worldwide scope."""
    return GLOBAL_REGION in (item.get("regions") or [])


def is_untagged(item: dict) -> bool:
    """No geography on any qualifying signal. Distinct from tagged global, and
    never matched by a `global` filter selection."""
    return not (item.get("regions") or [])


__all__ = [
    "CONFIDENCE_GATE", "GLOBAL_REGION", "INDEX", "REGION_IDS", "REGION_LABELS",
    "UNSPECIFIED_LABEL", "country_labels", "is_tagged_global", "is_untagged",
    "label", "labels", "options", "passes_any", "primary_label",
]
