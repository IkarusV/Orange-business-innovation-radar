"""Signal type taxonomy and the time-horizon (Now/Next/Later) derivation built
on top of it. Six mutually exclusive types, each defined by a distinguishing
question answerable from the article text alone - the questions, not the type
names, are what make the categories separable, so they are shipped verbatim
into the classification prompt (build_signal_type_block).

Same shape as common/trust.py: the taxonomy and the rules live here as the
single source of truth, imported by both the pipeline (which classifies and
persists) and the app (which reads and explains). Retuning a threshold or a
horizon prior therefore never means editing two copies.

Horizon is deliberately an INDEPENDENT dimension from attractiveness. Nothing
in this module reads an attractiveness score, an article count, or any
volume-derived proxy: the aggregation takes only signal types, signal dates,
event dates, source identities and per-signal confidences. A high-volume space
evidenced solely by tech_maturity signals must come out LATER; a thin space
with one recent tender must come out NEXT.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

# Ordered by tie-break priority: when an article plausibly satisfies more than
# one distinguishing question, the earlier entry wins. Concreteness and
# actor-specificity drive urgency, so the more concrete type takes precedence -
# an article announcing both a funding programme and a market forecast is a
# buying_signal, not a market_trend.
SIGNAL_TYPES = [
    {
        "slug": "buying_signal",
        "question": "Is a named organisation currently spending or committing money on this?",
        "detail": (
            "Tender or RFP published, contract awarded, framework agreement signed, procurement notice, "
            "budget line allocated, paid pilot commissioned. Also covers a named organisation selecting, "
            "signing for, equipping itself with or rolling out a purchased system - buying is buying whether "
            "or not a contract value is quoted."
        ),
        "positive": "Regional health authority awards EUR 4.2M contract for imaging analytics platform.",
        "negative": (
            "\"Analysts expect hospital AI spending to grow.\" -> market_trend (no named buyer, no committed money). "
            "\"Startup raises $33M to develop its diagnostic.\" -> tech_maturity (investment into building a "
            "technology is not procurement of it)."
        ),
    },
    {
        "slug": "regulation",
        "question": "Does this reference a specific law, mandate or standard issued by a regulatory body, with an identifiable enforcement or phase-in date?",
        "detail": "Directive, delegated act, national transposition, mandatory standard, sector-specific compliance obligation. Requires both an identifiable issuing body and a date (enforcement, phase-in or publication of the binding text).",
        "positive": "EU ESPR delegated acts confirm digital product passport timelines for textiles from 2028.",
        "negative": "\"Industry group calls for stricter traceability rules.\" -> market_trend (advocacy, not a binding instrument).",
    },
    {
        "slug": "proof_signal",
        "question": "Does this describe a completed or in-progress deployment with a measurable, reported result?",
        "detail": (
            "Deployment case study, pilot outcome with reported metrics, reference customer result, published "
            "benchmark from a real installation, completed funded project with results. The reported result does "
            "not have to be a number: a named organisation stating that a system it actually runs delivered an "
            "outcome (\"helped mitigate disruptions\", \"cut processing times to minutes\") is a proof signal. "
            "The test is whether the thing is already running somewhere identifiable, not whether a percentage "
            "is quoted."
        ),
        "positive": "Plant reports 18% downtime reduction after 12-month predictive maintenance rollout.",
        "negative": "\"Vendor claims its platform can reduce downtime by up to 20%.\" -> competitor_move (marketing claim, no deployment reported).",
    },
    {
        "slug": "competitor_move",
        "question": "Did a named vendor, competitor or peer organisation launch, acquire or announce something?",
        "detail": (
            "Product launch, acquisition, partnership, market entry, capability announcement by a named "
            "commercial actor. Also covers vendor marketing claims without deployment evidence. The named actor "
            "must be the SUBJECT of the article, and what it announced must be a concrete thing - a product, a "
            "deal, an acquisition, a market entry, a specific new capability. A stated priority or focus area, "
            "an opinion, a warning, a piece of guidance, or a vendor quoted as a commentator inside an article "
            "about something else is not a competitor move."
        ),
        "positive": "Telco X launches private 5G bundle for mining operators.",
        "negative": (
            "\"Private 5G deployments in mining grew 40% year over year.\" -> market_trend. "
            "\"Agency says protecting critical infrastructure is a priority.\" -> market_trend (a stated focus, "
            "not a concrete move)."
        ),
    },
    {
        "slug": "tech_maturity",
        "question": "Is this about a technology becoming viable - cost drop, model release, standard finalised, research breakthrough - rather than about anyone buying or deploying it yet?",
        "detail": "Cost curve movement, model or hardware release, standard finalisation, benchmark improvement in lab conditions, funded research programme, academic result.",
        "positive": "Edge inference cost per stream down ~45% with new accelerator generation.",
        "negative": "\"Manufacturer deploys edge vision across 12 sites.\" -> proof_signal.",
    },
    {
        "slug": "market_trend",
        "question": "Is the claim aggregate or statistical (market size, growth rate, adoption percentage) rather than about one named actor?",
        "detail": (
            "Market sizing, CAGR, adoption survey, aggregate spending forecast, analyst outlook, sector-wide "
            "observation with no single named actor. Also covers advisories, guidance and warnings from any "
            "body, legislation that has only been proposed or introduced, and explainers about why a technology "
            "matters - including ones that quote named vendors or agencies as commentators. A named actor "
            "appearing somewhere in the text does not make the article about that actor."
        ),
        "positive": "Traceability platform market growing 28% annually in Europe.",
        "negative": "\"Three tier-1 producers formed a DPP task force.\" -> buying_signal (named actors committing resources).",
    },
]

TIE_BREAK_ORDER = [entry["slug"] for entry in SIGNAL_TYPES]
SIGNAL_TYPE_SLUGS = set(TIE_BREAK_ORDER)
SIGNAL_TYPE_BY_SLUG = {entry["slug"]: entry for entry in SIGNAL_TYPES}

# Guards a vague "sometime in 2028" from being treated as a hard deadline.
EVENT_DATE_PRECISIONS = ["exact", "month", "quarter", "year", "none"]

NOW = "Now"
NEXT = "Next"
LATER = "Later"
HORIZONS = [NOW, NEXT, LATER]

# One step down the urgency ladder, used by the low-confidence demotion gate.
_DEMOTE = {NOW: NEXT, NEXT: LATER, LATER: LATER}


@dataclass(frozen=True)
class HorizonConfig:
    """Every threshold in the horizon rules, in one named place. These are
    first-cut values with no live distribution behind them yet - expect to
    recalibrate them against the real Now/Next/Later spread rather than
    treating them as settled.
    """
    confidence_gate: float = 0.5          # below this, a signal's prior is demoted one step
    recency_window_days: int = 365        # only signals this recent take part in horizon at all
    now_min_signals: int = 2              # converging evidence, not a single record
    now_min_sources: int = 2              # ...from genuinely different places
    now_recent_days: int = 90             # ...at least one of which is fresh
    next_min_signals: int = 2             # two forward-looking signals also reach Next
    next_window_days: int = 180
    regulation_now_months: int = 6        # enforcement this close is a Now problem
    regulation_next_months: int = 24      # beyond this it is Later, however certain the date


DEFAULT_HORIZON_CONFIG = HorizonConfig()

DAYS_PER_MONTH = 30.44


def build_signal_type_block() -> str:
    """The taxonomy as prompt text. The distinguishing question leads each
    entry because it is the part the model has to actually answer; the
    positive/negative pair is there to pin the boundary against the
    neighbouring type it is most often confused with."""
    blocks = []
    for index, entry in enumerate(SIGNAL_TYPES, 1):
        blocks.append(
            f"{index}. {entry['slug']}\n"
            f"   Distinguishing question: {entry['question']}\n"
            f"   Covers: {entry['detail']}\n"
            f"   Positive: {entry['positive']}\n"
            f"   Negative: {entry['negative']}"
        )
    return "\n".join(blocks)


def build_tie_break_line() -> str:
    return " > ".join(TIE_BREAK_ORDER)


def parse_date(value) -> Optional[datetime]:
    """Tolerant ISO parse to an aware UTC datetime. Accepts a date, a datetime,
    a 'Z'-suffixed string, or None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(text[:10])
            except ValueError:
                return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass
class SignalHorizon:
    """One signal's contribution to the horizon, with everything needed to
    explain it: the prior before and after the confidence gate."""
    prior: Optional[str]        # None when the signal takes no part (untyped, or outside the recency window)
    raw_prior: Optional[str]
    gated: bool                 # True when the low-confidence gate demoted it
    in_window: bool
    reason: str


def signal_horizon_prior(
    signal_type: Optional[str],
    signal_date=None,
    event_date=None,
    event_date_precision: Optional[str] = None,
    confidence: Optional[float] = None,
    now: Optional[datetime] = None,
    config: HorizonConfig = DEFAULT_HORIZON_CONFIG,
) -> SignalHorizon:
    """Per-signal horizon prior. Type drives it, except for regulation, where
    the binding date is the whole point: a mandate already in force is a Now
    problem and the same mandate five years out is not.

    A confidence below the gate demotes the prior one step (Now->Next,
    Next->Later). Low-confidence signals still count toward attractiveness -
    the gate applies to horizon only. Because the demotion always strips a Now
    prior, a gated signal can never be the sole trigger for a Now verdict; the
    aggregation asserts that rather than relying on it implicitly.
    """
    now = now or datetime.now(timezone.utc)
    if signal_type not in SIGNAL_TYPE_SLUGS:
        return SignalHorizon(None, None, False, False, "no valid signal type")

    parsed_signal_date = parse_date(signal_date)
    if parsed_signal_date is None:
        # Recency cannot be established, so the signal cannot be shown to be
        # current - it sits out horizon rather than being assumed fresh.
        return SignalHorizon(None, None, False, False, "no signal date")
    age_days = (now - parsed_signal_date).days
    if age_days > config.recency_window_days:
        return SignalHorizon(None, None, False, False, f"signal {age_days}d old, outside the {config.recency_window_days}d window")

    if signal_type in ("buying_signal", "proof_signal"):
        raw, reason = NOW, f"{signal_type} is concrete and current"
    elif signal_type in ("competitor_move", "market_trend"):
        raw, reason = NEXT, f"{signal_type} points at a forming market"
    elif signal_type == "tech_maturity":
        raw, reason = LATER, "tech_maturity precedes anyone buying or deploying"
    else:  # regulation
        raw, reason = _regulation_prior(event_date, event_date_precision, now, config)

    gated = confidence is not None and confidence < config.confidence_gate
    prior = _DEMOTE[raw] if gated else raw
    if gated:
        reason = f"{reason}; demoted from {raw} (confidence {confidence:.2f} < {config.confidence_gate})"
    return SignalHorizon(prior, raw, gated, True, reason)


def _regulation_prior(event_date, event_date_precision, now, config) -> tuple:
    if event_date_precision == "none":
        return LATER, "regulation with no usable enforcement date"
    parsed = parse_date(event_date)
    if parsed is None:
        return LATER, "regulation with no enforcement date"
    months_away = (parsed - now).days / DAYS_PER_MONTH
    when = parsed.date().isoformat()
    if months_away <= 0:
        return NOW, f"regulation already in force ({when})"
    if months_away <= config.regulation_now_months:
        return NOW, f"regulation binding {when} (~{months_away:.0f} mo)"
    if months_away <= config.regulation_next_months:
        return NEXT, f"regulation binding {when} (~{months_away:.0f} mo)"
    return LATER, f"regulation binding {when} (~{months_away:.0f} mo out)"


@dataclass
class HorizonVerdict:
    """The badge plus everything the UI needs to justify it. Per the brief, if
    a user cannot see why a topic is ranked where it is, the scoring is not
    good enough - so the counts, the distinct-source count and the rule that
    fired are all part of the result, not debug output."""
    horizon: str
    rule: str
    reason: str
    now_count: int = 0
    next_count: int = 0
    later_count: int = 0
    distinct_sources: int = 0
    gated_count: int = 0
    out_of_window_count: int = 0
    untyped_count: int = 0
    contributing: list = field(default_factory=list)

    def as_row(self) -> dict:
        return {
            "horizon": self.horizon,
            "horizon_rule": self.rule,
            "horizon_reason": self.reason,
            "horizon_now_count": self.now_count,
            "horizon_next_count": self.next_count,
            "horizon_later_count": self.later_count,
            "horizon_distinct_sources": self.distinct_sources,
            "horizon_gated_count": self.gated_count,
            "horizon_out_of_window_count": self.out_of_window_count,
            "horizon_untyped_count": self.untyped_count,
        }


def aggregate_horizon(
    signals: list,
    now: Optional[datetime] = None,
    config: HorizonConfig = DEFAULT_HORIZON_CONFIG,
) -> HorizonVerdict:
    """Opportunity-space horizon from its signals. Rules are evaluated in
    order and the first match wins.

    Now   - converging, recent, concrete evidence: at least now_min_signals
            with a Now prior, from at least now_min_sources distinct sources,
            at least one dated within now_recent_days.
    Next  - either a Now-prior signal exists but the Now bar is not met (a
            single tender, or two from the same source, or nothing recent
            enough), or at least next_min_signals with a Next prior inside
            next_window_days. This is the band that a threshold cut on a
            single score can never fill, which is the whole point of deriving
            horizon from types instead.
    Later - everything else: tech_maturity-only spaces, sparse evidence, and
            spaces whose only dated events are past regulation_next_months.

    `signals` are dicts with signal_type, signal_type_confidence, signal_date,
    event_date, event_date_precision, source_name. No other key is read.
    """
    now = now or datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(days=config.now_recent_days)
    next_cutoff = now - timedelta(days=config.next_window_days)

    by_prior = {NOW: [], NEXT: [], LATER: []}
    gated_count = out_of_window = untyped = 0
    contributing = []

    for signal in signals:
        evaluated = signal_horizon_prior(
            signal.get("signal_type"),
            signal_date=signal.get("signal_date"),
            event_date=signal.get("event_date"),
            event_date_precision=signal.get("event_date_precision"),
            confidence=signal.get("signal_type_confidence"),
            now=now,
            config=config,
        )
        if evaluated.prior is None:
            if evaluated.reason == "no valid signal type":
                untyped += 1
            else:
                out_of_window += 1
            continue
        if evaluated.gated:
            gated_count += 1
        entry = {
            "prior": evaluated.prior,
            "raw_prior": evaluated.raw_prior,
            "gated": evaluated.gated,
            "signal_type": signal.get("signal_type"),
            "source_name": signal.get("source_name"),
            "signal_date": signal.get("signal_date"),
            "reason": evaluated.reason,
        }
        by_prior[evaluated.prior].append(entry)
        contributing.append(entry)

    now_signals = by_prior[NOW]
    next_signals = by_prior[NEXT]
    # The gate always strips a Now prior, so this holds by construction - kept
    # explicit so a future change to _DEMOTE cannot quietly let a
    # low-confidence signal trigger a Now verdict on its own.
    now_signals = [entry for entry in now_signals if not entry["gated"]]

    now_sources = {entry["source_name"] for entry in now_signals if entry["source_name"]}
    now_recent = [entry for entry in now_signals if (parse_date(entry["signal_date"]) or now) >= recent_cutoff]

    counts = dict(
        now_count=len(by_prior[NOW]), next_count=len(next_signals), later_count=len(by_prior[LATER]),
        distinct_sources=len(now_sources), gated_count=gated_count,
        out_of_window_count=out_of_window, untyped_count=untyped, contributing=contributing,
    )

    if (
        len(now_signals) >= config.now_min_signals
        and len(now_sources) >= config.now_min_sources
        and now_recent
    ):
        return HorizonVerdict(
            NOW, "now_converging_evidence",
            f"{len(now_signals)} concrete signals across {len(now_sources)} sources, "
            f"{len(now_recent)} within {config.now_recent_days} days",
            **counts,
        )

    if now_signals:
        missing = []
        if len(now_signals) < config.now_min_signals:
            missing.append(f"only {len(now_signals)} of {config.now_min_signals} concrete signals")
        if len(now_sources) < config.now_min_sources:
            missing.append(f"only {len(now_sources)} of {config.now_min_sources} distinct sources")
        if not now_recent:
            missing.append(f"none within {config.now_recent_days} days")
        return HorizonVerdict(
            NEXT, "next_concrete_but_below_now_bar",
            "concrete evidence exists but does not converge: " + ", ".join(missing),
            **counts,
        )

    recent_next = [entry for entry in next_signals if (parse_date(entry["signal_date"]) or now) >= next_cutoff]
    if len(recent_next) >= config.next_min_signals:
        return HorizonVerdict(
            NEXT, "next_forming_market",
            f"{len(recent_next)} competitor/market signals within {config.next_window_days} days, "
            "no committed spend or deployment yet",
            **counts,
        )

    return HorizonVerdict(
        LATER, "later_default",
        _later_reason(by_prior, out_of_window, untyped, config),
        **counts,
    )


def _later_reason(by_prior, out_of_window, untyped, config) -> str:
    if by_prior[LATER] and not by_prior[NOW] and not by_prior[NEXT]:
        types = sorted({entry["signal_type"] for entry in by_prior[LATER]})
        return f"evidenced only by {', '.join(types)} - viability, not demand"
    if by_prior[NEXT]:
        return f"fewer than {config.next_min_signals} forward-looking signals within {config.next_window_days} days"
    if out_of_window or untyped:
        return (
            f"no signal inside the {config.recency_window_days}-day window carries a usable type "
            f"({out_of_window} too old, {untyped} untyped)"
        )
    return "no dated, typed evidence yet"
