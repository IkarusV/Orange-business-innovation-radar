"""Role mode: a named view configuration, never stored data.

A mode bundles three things - default filter values, a default sort key, and a
presentation profile that decides which regions of the opportunity detail page
lead, sit in normal position, or start collapsed. The same opportunity space
record renders differently under each mode; no field is written to the record.

The definitions live in radar_v2/config/role_modes.json, following the same
"vocabulary belongs in configuration" rule as the business domain taxonomy.

Two upstream features this module depends on did not exist when role mode was
first built; one has since landed:

  PERSONA_WEIGHTING_AVAILABLE - the use case x persona relevance table, its
      domain overlay and the dampened score multiplier now live in
      radar_v2/services/personas.py. Every persona weight threshold in the
      config is applied for real, the sales persona requirement still degrades
      to an inline prompt rather than a hard gate (per the spec: adjustable
      defaults, never a gate the user can't clear), and the persona-weighted
      sort ranks by the dampened multiplier.

  FIT_SCORE_AVAILABLE - a right-to-win / fit score per space. This now
      exists: orange_fit_score (radar_v2/services/attractiveness.py's
      orange_fit()) - match against Orange's own selected priority use cases
      and technologies - is this app's answer to "right to win", so the
      presales sort runs it directly instead of falling back to
      attractiveness. There is still no separate CRM/account/proof-point
      data source; that remains the honest gap the "Right to win & proof
      points" detail region and explanations.py's right-to-win clause
      describe - a different question from fit-to-priorities.

  EXPLANATION_FIELDS_AVAILABLE - "why hot now", "why this matters" and
      "recommended move" as three independent per-space fields. These now exist:
      radar_v2/services/explanations.py composes all three deterministically
      from the signal types, business domain, persona weights and horizon
      already on the record. "Recommended move" is a map keyed by role mode -
      the base-clause matrix answers per mode, so the same space produces a
      different move for a strategist and for a salesperson. Emphasis still only
      moves the regions around the page; every field is composed in every mode.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from radar_v2.constants import ROLE_MODES
from radar_v2.services import personas

PERSONA_WEIGHTING_AVAILABLE = True
FIT_SCORE_AVAILABLE = True
EXPLANATION_FIELDS_AVAILABLE = True

LEAD = "lead"
STANDARD = "standard"
COLLAPSED = "collapsed"
EMPHASIS_VALUES = (LEAD, STANDARD, COLLAPSED)

FALLBACK_SORT_KEY = "attractiveness"


class RoleModeConfigError(ValueError):
    """The role mode configuration is unusable - raised loudly at import, since
    a silently half-loaded mode would render a page nobody can explain."""


def _load() -> dict[str, Any]:
    config = json.loads(ROLE_MODES.read_text(encoding="utf-8"))
    regions = config.get("regions") or []
    modes = config.get("modes") or []
    if not regions or not modes:
        raise RoleModeConfigError("role_modes.json must define regions and modes")
    region_keys = [region["key"] for region in regions]
    if len(set(region_keys)) != len(region_keys):
        raise RoleModeConfigError("duplicate region key in role_modes.json")
    for mode in modes:
        presentation = mode.get("presentation") or {}
        missing = set(region_keys) - set(presentation)
        if missing:
            raise RoleModeConfigError(f"mode {mode.get('id')} is missing regions: {sorted(missing)}")
        unknown = set(presentation) - set(region_keys)
        if unknown:
            raise RoleModeConfigError(f"mode {mode.get('id')} declares unknown regions: {sorted(unknown)}")
        invalid = {key: value for key, value in presentation.items() if value not in EMPHASIS_VALUES}
        if invalid:
            # "hidden" is not an allowed value: the trust and actionability criteria
            # require signals and sources to stay reachable in every mode.
            raise RoleModeConfigError(f"mode {mode.get('id')} uses invalid emphasis: {invalid}")
    if config.get("default_mode") not in {mode["id"] for mode in modes}:
        raise RoleModeConfigError("default_mode is not one of the configured modes")
    return config


CONFIG = _load()
REGIONS: list[dict[str, Any]] = CONFIG["regions"]
REGION_KEYS: list[str] = [region["key"] for region in REGIONS]
MODES: list[dict[str, Any]] = CONFIG["modes"]
MODE_IDS: list[str] = [mode["id"] for mode in MODES]
DEFAULT_MODE: str = CONFIG["default_mode"]

_BY_ID = {mode["id"]: mode for mode in MODES}


def mode(mode_id: str) -> dict[str, Any]:
    return _BY_ID.get(mode_id, _BY_ID[DEFAULT_MODE])


def label(mode_id: str) -> str:
    return str(mode(mode_id)["label"])


def description(mode_id: str) -> str:
    return str(mode(mode_id).get("description", ""))


def icon(mode_id: str) -> str:
    return str(mode(mode_id).get("icon", "circle"))


def filter_defaults(mode_id: str) -> dict[str, Any]:
    defaults = dict(mode(mode_id).get("filters", {}))
    defaults["domains"] = list(defaults.get("domains", []))
    return defaults


def persona_required(mode_id: str) -> bool:
    return bool(filter_defaults(mode_id).get("persona_required"))


def persona_threshold(mode_id: str) -> Optional[float]:
    """The configured threshold, regardless of whether it can be applied yet.
    Callers must check PERSONA_WEIGHTING_AVAILABLE before acting on it."""
    value = filter_defaults(mode_id).get("persona_weight_threshold")
    return float(value) if value is not None else None


def list_density(mode_id: str) -> str:
    return str(mode(mode_id).get("list_density", "grid"))


def presentation(mode_id: str) -> dict[str, str]:
    return dict(mode(mode_id)["presentation"])


def emphasis(mode_id: str, region_key: str) -> str:
    return presentation(mode_id).get(region_key, STANDARD)


def region_label(region_key: str) -> str:
    return next((region["label"] for region in REGIONS if region["key"] == region_key), region_key)


def region_hint(region_key: str) -> str:
    return next((region.get("hint", "") for region in REGIONS if region["key"] == region_key), "")


def sort_plan(mode_id: str) -> dict[str, Any]:
    """Which sort actually runs, and why it may not be the configured one.

    A configured key whose feature does not exist yet is never silently swapped:
    the fallback carries a note the UI is expected to show.
    """
    configured = mode(mode_id).get("sort", {})
    key = str(configured.get("key", FALLBACK_SORT_KEY))
    label_text = str(configured.get("label", "Attractiveness score"))
    if key == "persona_weighted" and not PERSONA_WEIGHTING_AVAILABLE:
        return {
            "configured_key": key, "key": FALLBACK_SORT_KEY, "label": label_text,
            "effective_label": "Attractiveness score",
            "note": "Persona weighting is not implemented yet - sorted by attractiveness score instead.",
        }
    if key == "fit_score" and not FIT_SCORE_AVAILABLE:
        return {
            "configured_key": key, "key": FALLBACK_SORT_KEY, "label": label_text,
            "effective_label": "Attractiveness score",
            "note": "No right-to-win / fit score exists yet - sorted by attractiveness score instead.",
        }
    return {
        "configured_key": key, "key": key, "label": label_text,
        "effective_label": label_text, "note": "",
    }


def sort_opportunities(items: list[dict], mode_id: str, persona: str = "") -> list[dict]:
    """Apply the mode's effective sort. Article count stays the tie-breaker so
    ordering matches what team_repository already produces for equal scores.

    persona is the picker's selected label (the filter select's value, same
    convention as every other filter in this app) - resolved to an id here so
    callers never need to know the id/label split exists.
    """
    key = sort_plan(mode_id)["key"]
    if key == FALLBACK_SORT_KEY:
        return sorted(items, key=lambda item: (-item.get("relevance", 0), -item.get("article_count", 0)))
    if key == "persona_weighted":
        return personas.sort_by_persona(items, personas.id_for_label(persona))
    if key == "fit_score":
        return sorted(items, key=lambda item: (-item.get("orange_fit_score", 0), -item.get("article_count", 0)))
    # Any other key implies a feature that reached availability without a sort
    # implementation here - fail visibly in tests rather than reorder silently.
    raise RoleModeConfigError(f"no sort implementation for key: {key}")


def persona_threshold_passes(item: dict, mode_id: str, persona: str) -> bool:
    """Persona relevance gate. No persona selected is never a constraint - a
    mode's configured threshold only applies once the user has actually picked
    someone to weigh relevance against. A mode with no configured threshold
    (strategist) still applies the dimension's own default once a persona is
    selected, per the spec: mode thresholds only ever raise the bar, they
    don't turn the dimension off entirely."""
    if not PERSONA_WEIGHTING_AVAILABLE or not persona:
        return True
    threshold = persona_threshold(mode_id)
    if threshold is None:
        threshold = personas.DEFAULT_WEIGHT_THRESHOLD
    return personas.passes(item, personas.id_for_label(persona), threshold)


def persona_options() -> list[str]:
    """Persona labels in taxonomy order - the sales persona picker (and any
    other persona select) renders straight from this, same convention as every
    other filter select in this app (value == display label)."""
    if not PERSONA_WEIGHTING_AVAILABLE:
        return []
    return [option["label"] for option in personas.options()]


__all__ = [
    "COLLAPSED", "CONFIG", "DEFAULT_MODE", "EMPHASIS_VALUES", "EXPLANATION_FIELDS_AVAILABLE",
    "FIT_SCORE_AVAILABLE", "LEAD", "MODES", "MODE_IDS", "PERSONA_WEIGHTING_AVAILABLE",
    "REGIONS", "REGION_KEYS", "STANDARD", "RoleModeConfigError",
    "description", "emphasis", "filter_defaults", "icon", "label", "list_density", "mode",
    "persona_options", "persona_required", "persona_threshold", "persona_threshold_passes",
    "presentation", "region_hint", "region_label", "sort_opportunities", "sort_plan",
]
