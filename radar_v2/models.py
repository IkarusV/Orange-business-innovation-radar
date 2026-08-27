from __future__ import annotations

from typing import Any, TypedDict


class AttractivenessComponent(TypedDict):
    key: str
    label: str
    value: int
    weight: int
    available: bool


class HorizonCheck(TypedDict):
    """One line of the Now/Next/Later explanation: a count the rules acted on,
    and whether it cleared the threshold the badge depends on."""
    key: str
    label: str
    value: int
    detail: str
    met: bool


class SignalTypeCount(TypedDict):
    """How many of a space's signals carry one signal type, with the
    distinguishing question that assigned it."""
    key: str
    label: str
    value: int
    question: str


class TaxonomyOption(TypedDict):
    """One selectable entry from the closed taxonomy, with Orange's current
    priority selection state (Company tab -> Orange priorities)."""
    id: str
    label: str
    selected: bool


class PersonaWeight(TypedDict):
    """One buyer persona's derived relevance to a space. `source` records which
    table produced the weight - use_case, domain or both - so the UI can explain
    why the topic is flagged for this persona."""
    id: str
    label: str
    weight: float
    source: str


class RoleModeOption(TypedDict):
    """One selectable role mode for the mode switcher. Pure view configuration -
    nothing here is persisted against an opportunity space."""
    id: str
    label: str
    description: str
    icon: str
    selected: bool


class Opportunity(TypedDict):
    id: int
    vertical: str
    use_case_id: str
    use_case: str
    technology_id: str
    technology: str
    primary_domain: str
    primary_domain_label: str
    domains: list[str]
    domain_labels: list[str]
    persona_weights: list[PersonaWeight]
    persona_ids: list[str]
    # Geography. primary_region is "" for a space no signal could place, which
    # is a valid state rendered as "Global / unspecified" - deliberately not the
    # same as a space whose regions include the explicit "global" tag.
    primary_region: str
    primary_region_label: str
    regions: list[str]
    region_labels: list[str]
    countries: list[str]
    article_count: int
    relevance: int
    confidence: int
    horizon: str
    horizon_reason: str | None
    horizon_rule: str
    horizon_breakdown: list[HorizonCheck]
    signal_mix: list[SignalTypeCount]
    momentum: str
    summary: str
    updated: str
    breakdown: list[AttractivenessComponent]
    # Orange Business fit / right-to-win: standalone from Attractiveness (see
    # radar_v2/services/attractiveness.py's orange_fit()), never one of the
    # weighted components above.
    orange_fit_score: int
    # Whether Orange has configured ANY priority use case/technology at all
    # (company-wide, not per-space). Read by explanations.py's
    # orange_fit_clause() so a space's Orange Fit score is only described as a
    # real priorities match when one was actually possible.
    orange_priorities_configured: bool
    # Radar/Watchlist publication gate: independent of the Attractiveness
    # score, purely about evidence independence. Nothing is hidden by either
    # value - see radar_v2/services/attractiveness.py's radar_watchlist_gate().
    publication_status: str
    gate_breakdown: list[HorizonCheck]
    # The three composed explanation fields. "recommended move" is a map keyed by
    # role mode, because the same space is deliberately meant to produce a
    # different move for a strategist and for a salesperson; recommended_move is
    # that map resolved for the mode currently in view.
    why_hot_now: str
    why_this_matters: str
    recommended_moves: dict[str, str]
    recommended_move: str
    # Opportunity-level annual addressable-potential record imported from the
    # analysis2 pipeline. It is intentionally separate from Attractiveness and
    # Orange Fit. Pending/unavailable is a valid, rendered state.
    market_size: dict[str, Any]


class Evidence(TypedDict):
    title: str
    source: str
    source_type: str
    url: str
    date: str
    excerpt: str
    confidence: int


class SourceSummary(TypedDict):
    source: str
    label: str
    count: int
    accent: str


class DocumentItem(TypedDict):
    id: int
    company: str
    name: str
    kind: str
    status: str
    size: str
    updated: str
    selected: bool
    processed_name: str
    context_enabled: bool
    context_scope: str


class SearchResult(TypedDict):
    title: str
    url: str
    source: str
    date: str
    excerpt: str


class ReportItem(TypedDict):
    id: int
    title: str
    company: str
    sources: int
    created: str
    status: str


class ReportMetric(TypedDict):
    label: str
    value: str
    detail: str


class ReportBullet(TypedDict):
    title: str
    detail: str


class ReportRisk(TypedDict):
    title: str
    detail: str
    level: str


class ReportRange(TypedDict):
    label: str
    low: float
    high: float
    unit: str
    detail: str
