"""App-side explanation fields: "why hot now", "why this matters" and
"recommended move", composed deterministically from data the pipeline already
persists. No model call, no stored text, no new extraction step.

Each field is built from typed CLAUSES - one clause per qualifying data element,
joined with a fixed connector - rather than one sentence with slots. Thin data
therefore produces a short result instead of a stretched one, and richer data
produces more clauses up to a cap. A missing input always degrades to a stated
fallback; nothing here invents a count, an actor or a positive-sounding filler.

The three fields differ in how much they are allowed to vary:

  why hot now      - 0..3 clauses, ordered by the signal-type tie-break priority
                     in Pipelineteamfile/common/signal_types.py (reused, never
                     re-declared here), " · " between clauses.
  why this matters - always exactly 2 clauses, " — " between them. It describes
                     durable domain fit rather than time-bound evidence, so its
                     clause count does not move with the data.
  recommended move - one base clause from the role mode x horizon matrix plus
                     one action clause keyed on the dominant signal type. It is
                     a MAP of three strings, one per role mode: a strategist and
                     a salesperson are meant to get different answers on the same
                     space. Role mode never changes which fields are computed.

Dependency state at the time of writing. Signal typing, domain resolution,
persona weighting and horizon are all live, so all four named dependencies feed
real values. Right-to-win is not: no account, deal, reference case, offering or
partner data exists anywhere in this codebase, so clause 2 of "why this matters"
is the honest all-zero fallback on every space today. RIGHT_TO_WIN_ELEMENTS
below is the contract a future catalogue/CRM read fills in - counts are never
synthesised from unrelated fields in the meantime.

The classifier also persists no separately extracted entity / metric / stat /
action slot, only the free-text signal_type_rationale. Per the spec's own
instruction the rationale, truncated, stands in for those slots; source_name is
deliberately NOT used as the actor, because it names the publication (CORDIS,
Defense Daily) and not the organisation that acted.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Optional

from radar_v2.constants import TEAM_PIPELINE
from radar_v2.services import domains as domain_service
from radar_v2.services import personas as persona_service
from radar_v2.services import role_modes

_TEAM_ROOT = str(TEAM_PIPELINE)
if _TEAM_ROOT not in sys.path:
    sys.path.insert(0, _TEAM_ROOT)

from common.signal_types import (  # noqa: E402  (needs the sys.path insert above)
    DEFAULT_HORIZON_CONFIG,
    HORIZONS,
    LATER,
    NEXT,
    NOW,
    SIGNAL_TYPE_SLUGS,
    TIE_BREAK_ORDER,
    parse_date,
)


class ExplanationConfigError(ValueError):
    """A clause table has drifted from the vocabulary it is keyed on - raised
    loudly at import, since a silently missing row would render a fallback that
    reads like a real answer."""


# Field 1 -------------------------------------------------------------------

MAX_HOT_NOW_CLAUSES = 3
HOT_NOW_JOIN = " · "
NO_RECENT_SIGNAL = "No recent external signal on record."

# Same recency window as horizon aggregation, so a space cannot be described as
# hot on evidence the timing badge already ruled out of scope.
RECENCY_WINDOW_DAYS = DEFAULT_HORIZON_CONFIG.recency_window_days

# Fixed micro-template per signal type. The lead-in is what makes the clause
# self-describing once the entity/metric/stat slot falls back to the rationale:
# without it the reader cannot tell a competitor move from a proof point, which
# is the whole reason field 1 is ordered by type in the first place.
HOT_NOW_LEAD_INS = {
    "buying_signal": "Committed spend",
    "regulation": "Mandate",
    "proof_signal": "Reported result",
    "competitor_move": "Competitor move",
    "market_trend": "Market trend",
    "tech_maturity": "Tech maturity",
}

# Locale-independent on purpose: strftime("%b") follows the process locale and
# would render a different string on a differently configured machine.
MONTH_ABBREVIATIONS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

RATIONALE_MAX_WORDS = 8
ELLIPSIS = "…"


# Field 2 -------------------------------------------------------------------

CLAUSE_JOIN = " — "

DOMAIN_CLAUSES = {
    "ox-smart-industries": "An Industrial/OX opportunity for {vertical}",
    "connectivity-solutions": "A Connectivity play for {vertical}",
    "cybersecurity": "A Cybersecurity opportunity for {vertical}",
    "cloud": "A Cloud opportunity for {vertical}",
    "cx-customer-experience": "A Customer Experience play for {vertical}",
    "ex-employee-experience": "An Employee Experience opportunity for {vertical}",
}
GENERIC_DOMAIN_CLAUSE = "An opportunity for {vertical}"
UNKNOWN_VERTICAL = "this sector"

# No account/deal/reference-case/offering/partner data source exists yet, so
# right_to_win_phrases() is empty for every space today and clause 2 falls
# back to the space's own Orange Fit score instead (right-to-win IS Orange Fit
# for this app - see attractiveness.py's orange_fit()). Only phrased as an
# actual priorities match when Orange has configured priorities at all -
# orange_fit_score's domain-coverage fallback (used while none are configured)
# is a weaker capability proxy and is named as such rather than dressed up as
# a real match.
ORANGE_FIT_STRONG_THRESHOLD = 75   # >= this reads as a strong match, not just "some" overlap
ORANGE_FIT_NOT_CONFIGURED = "no Orange priorities configured yet — fit shown is a business-domain estimate"
ORANGE_FIT_STRONG = "strong fit with Orange's priorities"
ORANGE_FIT_PARTIAL = "partial fit with Orange's priorities"
ORANGE_FIT_NONE = "no match with Orange's current priorities"
MAX_RIGHT_TO_WIN_ELEMENTS = 3

# The five element kinds and their micro-phrases. Counting elements carry an
# int, named elements a string; both are read from item["right_to_win"], which
# nothing populates today.
RIGHT_TO_WIN_ELEMENTS = {
    "accounts": {"kind": "count", "template": "{n} {vertical} account{plural}"},
    "recent_deals": {"kind": "count", "template": "{n} recent deal{plural}"},
    "reference_cases": {"kind": "count", "template": "{n} reference case{plural}"},
    "offering_match": {"kind": "name", "template": "{name} in our portfolio"},
    "partner_match": {"kind": "name", "template": "{name} partnership"},
}
RIGHT_TO_WIN_AVAILABLE = False


# Field 3 -------------------------------------------------------------------

BASE_CLAUSES = {
    "strategist": {
        NOW: "Prioritise for {persona} this quarter",
        NEXT: "Track for {persona}; revisit next quarter",
        LATER: "Add to the watchlist for {persona}",
    },
    "sales": {
        NOW: "Open with {persona}",
        NEXT: "Warm up {persona} on this",
        LATER: "Not yet — hold for {persona}",
    },
    "presales": {
        NOW: "Lead the RFP angle for {persona} with this",
        NEXT: "Keep in back pocket for {persona}",
        LATER: "Note as a future differentiator for {persona}",
    },
}

ACTION_CLAUSES = {
    "buying_signal": "reference the live tender directly",
    "regulation": "frame it as compliance timing, not optional",
    "proof_signal": "lead with the reported result",
    "competitor_move": "position against the competitor's move",
    "market_trend": "use the market data as the opener",
    "tech_maturity": "keep the pitch exploratory, evidence is still building",
}

# The most conservative row: used when a space has no qualifying signal at all,
# so the move never claims more urgency than the evidence supports.
DEFAULT_DOMINANT_TYPE = "tech_maturity"

# Horizon is stored title-cased ("Now"/"Next"/"Later"). Matching is normalised
# rather than exact so a casing change upstream cannot silently push every space
# into the neutral middle column.
NEUTRAL_HORIZON = NEXT

GENERIC_PERSONA = "the relevant stakeholder"

# Conversational short forms for the composed sentence only. The taxonomy labels
# are full formal titles ("COO & Production Executive"), which read as stiff
# inside "Prioritise for ... this quarter". Display-layer sugar for this one
# sentence: the persona badges, filters and ranking all keep the taxonomy label.
PERSONA_SHORT_FORMS = {
    "cio": "the CIO",
    "it-network-executive": "the IT & network lead",
    "cyber-executive": "the CISO",
    "cdo": "the CDO",
    "coo-production-executive": "the COO",
    "cmo-cx-executive": "the CMO",
    "quality-manager": "the quality manager",
    "industrial-safety-manager": "the safety manager",
}


def _validate() -> None:
    """Every clause table is keyed on a closed vocabulary owned elsewhere. A
    row added to one of those vocabularies without a matching clause here is a
    configuration error, not a runtime fallback."""
    if set(HOT_NOW_LEAD_INS) != SIGNAL_TYPE_SLUGS:
        raise ExplanationConfigError("HOT_NOW_LEAD_INS does not cover the signal type taxonomy")
    if set(ACTION_CLAUSES) != SIGNAL_TYPE_SLUGS:
        raise ExplanationConfigError("ACTION_CLAUSES does not cover the signal type taxonomy")
    if set(DOMAIN_CLAUSES) != set(domain_service.DOMAIN_IDS):
        raise ExplanationConfigError("DOMAIN_CLAUSES does not cover the business domain taxonomy")
    if set(PERSONA_SHORT_FORMS) != set(persona_service.PERSONA_IDS):
        raise ExplanationConfigError("PERSONA_SHORT_FORMS does not cover the persona taxonomy")
    if set(BASE_CLAUSES) != set(role_modes.MODE_IDS):
        raise ExplanationConfigError("BASE_CLAUSES does not cover the configured role modes")
    for mode_id, row in BASE_CLAUSES.items():
        if set(row) != set(HORIZONS):
            raise ExplanationConfigError(f"BASE_CLAUSES[{mode_id}] does not cover every horizon")


_validate()


def _snippet(text: Optional[str], max_words: int = RATIONALE_MAX_WORDS) -> str:
    """The classifier's free-text rationale cut to a clause-sized phrase.

    This stands in for the entity / metric / stat / action slots the spec
    expects, none of which are persisted as separate fields. It is a truncation,
    never a parse: no attempt is made to pick the actor out of the sentence,
    because a wrong actor is worse than a slightly blunt clause.
    """
    words = str(text or "").split()
    if not words:
        return ""
    truncated = words[:max_words]
    phrase = " ".join(truncated).rstrip(".,;:")
    return f"{phrase}{ELLIPSIS}" if len(words) > max_words else phrase


def _month_year(value) -> str:
    parsed = parse_date(value)
    if parsed is None:
        return ""
    return f"{MONTH_ABBREVIATIONS[parsed.month - 1]} {parsed.year}"


def _year(value) -> str:
    parsed = parse_date(value)
    return str(parsed.year) if parsed else ""


def qualifying_signals(article_rows: list[dict], now: Optional[datetime] = None) -> list[dict]:
    """Typed signals inside the recency window, ordered as field 1 renders them.

    Ordering is the signal-type tie-break priority first - the same constant the
    classifier and the horizon rules use - then most recent first, so the order
    is total and two runs over the same evidence cannot disagree.
    """
    now = now or datetime.now(timezone.utc)
    dated = []
    for row in article_rows:
        signal_type = row.get("signal_type")
        if signal_type not in SIGNAL_TYPE_SLUGS:
            continue
        signal_date = parse_date(row.get("signal_date"))
        if signal_date is None:
            continue
        if (now - signal_date).days > RECENCY_WINDOW_DAYS:
            continue
        dated.append((TIE_BREAK_ORDER.index(signal_type), -signal_date.timestamp(), row))
    dated.sort(key=lambda entry: (entry[0], entry[1]))
    return [entry[2] for entry in dated]


def hot_now_clause(signal: dict) -> str:
    """One clause for one signal. The date slots are real persisted values; the
    descriptive half prefers signal_type_plain_summary - a sentence the
    classifier (or, for a deterministic source, a hand-authored template in
    signal_route.py) wrote specifically for a non-technical reader - and falls
    back to a truncation of signal_type_rationale (see _snippet) for any row
    that predates that field."""
    signal_type = signal.get("signal_type")
    lead_in = HOT_NOW_LEAD_INS.get(signal_type, "Signal")
    if signal_type == "buying_signal":
        when = _month_year(signal.get("signal_date"))
        lead_in = f"{lead_in} ({when})" if when else lead_in
    elif signal_type == "regulation":
        # event_date is the binding date and the one worth showing; signal_date
        # is the fallback the spec names when the classifier found no event.
        when = _year(signal.get("event_date")) or _year(signal.get("signal_date"))
        lead_in = f"{lead_in} from {when}" if when else lead_in
    plain_summary = str(signal.get("signal_type_plain_summary") or "").strip()
    detail = plain_summary or _snippet(signal.get("signal_type_rationale"))
    return f"{lead_in}: {detail}" if detail else lead_in


def hot_now_clauses(ranked_signals: list[dict]) -> list[str]:
    """The clauses field 1 renders, in order, capped.

    Byte-identical clauses are collapsed. Deterministic sources emit a fixed
    rationale for every row they produce ("CORDIS project status SIGNED - funded
    research still running"), so without this a space evidenced by three CORDIS
    records renders the same sentence three times - which reads as padding, the
    exact failure the clause-per-element rule exists to avoid. Collapsing keeps
    looking down the ranked list, so a distinct fourth signal is preferred over a
    repeat of the first.
    """
    clauses: list[str] = []
    for signal in ranked_signals:
        clause = hot_now_clause(signal)
        if clause in clauses:
            continue
        clauses.append(clause)
        if len(clauses) == MAX_HOT_NOW_CLAUSES:
            break
    return clauses


def why_hot_now(ranked_signals: list[dict]) -> str:
    """Field 1. One clause per qualifying signal, capped, never padded."""
    clauses = hot_now_clauses(ranked_signals)
    return HOT_NOW_JOIN.join(clauses) if clauses else NO_RECENT_SIGNAL


def right_to_win_phrases(item: dict) -> list[str]:
    """Every non-zero right-to-win element as a short phrase, strongest first,
    capped. Returns [] for every space today: nothing writes item["right_to_win"]
    because no accounts, deals, reference cases, offering catalogue or partner
    ecosystem exists in this codebase yet."""
    elements = item.get("right_to_win") or {}
    vertical = str(item.get("vertical") or UNKNOWN_VERTICAL)
    scored = []
    for key, spec in RIGHT_TO_WIN_ELEMENTS.items():
        value = elements.get(key)
        if not value:
            continue
        if spec["kind"] == "count":
            count = int(value)
            if count <= 0:
                continue
            phrase = spec["template"].format(
                n=count, vertical=vertical, plural="" if count == 1 else "s",
            )
            scored.append((count, key, phrase))
        else:
            # Named elements have no magnitude to rank on; they sort after any
            # count rather than being given an invented weight.
            scored.append((0, key, spec["template"].format(name=str(value))))
    scored.sort(key=lambda entry: (-entry[0], entry[1]))
    return [phrase for _, _, phrase in scored[:MAX_RIGHT_TO_WIN_ELEMENTS]]


def orange_fit_clause(item: dict) -> str:
    """Clause 2's fallback when right_to_win_phrases() is empty (every space
    today): the space's own Orange Fit score, tiered into a short phrase,
    rather than one static sentence that never changes between spaces."""
    if not item.get("orange_priorities_configured"):
        return ORANGE_FIT_NOT_CONFIGURED
    score = item.get("orange_fit_score") or 0
    if score >= ORANGE_FIT_STRONG_THRESHOLD:
        return ORANGE_FIT_STRONG
    if score > 0:
        return ORANGE_FIT_PARTIAL
    return ORANGE_FIT_NONE


def why_this_matters(item: dict) -> str:
    """Field 2. Always exactly two clauses."""
    vertical = str(item.get("vertical") or UNKNOWN_VERTICAL)
    template = DOMAIN_CLAUSES.get(item.get("primary_domain") or "", GENERIC_DOMAIN_CLAUSE)
    phrases = right_to_win_phrases(item)
    return CLAUSE_JOIN.join([
        template.format(vertical=vertical),
        ", ".join(phrases) if phrases else orange_fit_clause(item),
    ])


def normalise_horizon(horizon: Optional[str]) -> str:
    for candidate in HORIZONS:
        if str(horizon or "").strip().lower() == candidate.lower():
            return candidate
    return NEUTRAL_HORIZON


def persona_phrase(item: dict) -> str:
    """The strongest persona for this space, in short conversational form.
    team_repository attaches persona_weights strongest-first, so the first row
    is the top persona."""
    weights = item.get("persona_weights") or []
    if not weights:
        return GENERIC_PERSONA
    top = weights[0]
    return PERSONA_SHORT_FORMS.get(top.get("id", ""), str(top.get("label") or GENERIC_PERSONA))


def recommended_move(item: dict, mode_id: str, dominant_type: Optional[str]) -> str:
    """Field 3 for one role mode. dominant_type is the type of the signal that
    ranked first in field 1 - passed in rather than recomputed, so the two
    fields can never disagree about which signal is leading."""
    row = BASE_CLAUSES.get(mode_id) or BASE_CLAUSES[role_modes.DEFAULT_MODE]
    base = row[normalise_horizon(item.get("horizon"))].format(persona=persona_phrase(item))
    action = ACTION_CLAUSES.get(dominant_type or "", ACTION_CLAUSES[DEFAULT_DOMINANT_TYPE])
    return f"{base}{CLAUSE_JOIN}{action}."


def recommended_moves(item: dict, dominant_type: Optional[str]) -> dict[str, str]:
    """Field 3 for every role mode. The matrix deliberately produces a different
    answer per mode for the same space, so the field is a map rather than one
    string - computed once per space, not per page render."""
    return {
        mode_id: recommended_move(item, mode_id, dominant_type)
        for mode_id in role_modes.MODE_IDS
    }


def compose(article_rows: list[dict], item: dict, now: Optional[datetime] = None) -> dict:
    """All three fields for one space. Every field is computed regardless of
    which mode the viewer happens to be in - role mode only decides where they
    land on the page."""
    ranked = qualifying_signals(article_rows, now=now)
    dominant_type = ranked[0].get("signal_type") if ranked else None
    moves = recommended_moves(item, dominant_type)
    return {
        "why_hot_now": why_hot_now(ranked),
        "why_this_matters": why_this_matters(item),
        "recommended_moves": moves,
        "recommended_move": moves[role_modes.DEFAULT_MODE],
    }


__all__ = [
    "ACTION_CLAUSES", "BASE_CLAUSES", "CLAUSE_JOIN", "DOMAIN_CLAUSES", "GENERIC_DOMAIN_CLAUSE",
    "GENERIC_PERSONA", "HOT_NOW_JOIN", "HOT_NOW_LEAD_INS", "MAX_HOT_NOW_CLAUSES",
    "MAX_RIGHT_TO_WIN_ELEMENTS", "NO_RECENT_SIGNAL", "PERSONA_SHORT_FORMS",
    "ORANGE_FIT_STRONG_THRESHOLD", "ORANGE_FIT_NOT_CONFIGURED", "ORANGE_FIT_STRONG",
    "ORANGE_FIT_PARTIAL", "ORANGE_FIT_NONE",
    "RECENCY_WINDOW_DAYS", "RIGHT_TO_WIN_AVAILABLE", "RIGHT_TO_WIN_ELEMENTS",
    "ExplanationConfigError", "compose", "hot_now_clause", "hot_now_clauses",
    "normalise_horizon", "orange_fit_clause", "persona_phrase",
    "qualifying_signals", "recommended_move", "recommended_moves", "right_to_win_phrases",
    "why_hot_now", "why_this_matters",
]
