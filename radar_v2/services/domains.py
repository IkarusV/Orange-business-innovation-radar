"""App-side business domains: the six Orange Business domains as a filterable
dimension on every opportunity space.

The vocabulary and both mapping tables live in
Pipelineteamfile/opportunity_classifier/config/taxonomy.json and the derivation
rules in Pipelineteamfile/common/business_domains.py, so the pipeline (which
derives and persists) and the app (which reads and filters) can never drift
apart. Nothing here hardcodes a domain: the filter options are read from the
taxonomy exactly like the Orange priority pickers are.

Reads normally come from the persisted opportunity_space_domains join table.
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

from common.business_domains import DomainIndex, build_index  # noqa: E402  (needs the sys.path insert above)


def _index() -> DomainIndex:
    return build_index(json.loads(TAXONOMY.read_text(encoding="utf-8")))


INDEX = _index()
DOMAIN_IDS = INDEX.ids
DOMAIN_LABELS = INDEX.labels


def options() -> list[dict]:
    """Filter options in taxonomy order - the brief's own domain ordering."""
    return [{"id": domain_id, "label": INDEX.label(domain_id)} for domain_id in DOMAIN_IDS]


def labels(domain_ids: list[str]) -> list[str]:
    return [INDEX.label(domain_id) for domain_id in domain_ids]


def derive(technology_id: str | None, use_case_id: str | None) -> tuple[str, list[str]]:
    """Fallback derivation for spaces with no persisted domain rows. Tolerant
    where the pipeline is strict: an assignment outside the closed taxonomy
    yields no domains rather than breaking the page - the pipeline backfill is
    where that data error is meant to surface."""
    try:
        resolution = INDEX.resolve(technology_id, use_case_id)
    except Exception:
        return "", []
    return resolution.primary, list(resolution.domains)


__all__ = ["DOMAIN_IDS", "DOMAIN_LABELS", "INDEX", "derive", "labels", "options"]
