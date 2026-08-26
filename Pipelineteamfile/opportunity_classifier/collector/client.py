import json
import os
import re
import time
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

from common.geography import CODE_ALIASES, INFERRED, ISO_ALPHA2, build_region_block
from common.signal_types import (
    EVENT_DATE_PRECISIONS,
    SIGNAL_TYPE_SLUGS,
    build_signal_type_block,
    build_tie_break_line,
    parse_date,
)

MODEL = os.environ.get("NAVY_MODEL", "glm-5.1")
TEMPERATURE = 0.1
REASONING_EFFORT = "none"  # default reasoning produced ~700 hidden tokens/call for no quality gain measured
CONFIDENCE_THRESHOLD = 0.5
MAX_FORMAT_RETRIES = 2  # malformed JSON / invalid id
MAX_TRANSIENT_RETRIES = 6  # 429 / 5xx / network

CLIENT_CONTEXT_BLOCK = (
    "\nCLIENT CONTEXT (may be used to resolve ambiguity or judge relevance; "
    "never overrides the taxonomy rules above — no new ids, no forced matches)\n\n{content}\n"
)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def make_client(api_key: str, base_url: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=base_url)


@dataclass
class ClassificationResult:
    use_case_id: Optional[str]
    technology_id: Optional[str]
    confidence: Optional[float]
    evidence: str
    status: str  # classified | no_match | needs_review
    client_relevance: Optional[float] = None
    client_relevance_reason: Optional[str] = None
    total_tokens: int = 0
    signal_type: Optional[str] = None
    signal_type_confidence: Optional[float] = None
    signal_date: Optional[str] = None
    event_date: Optional[str] = None
    event_date_precision: str = "none"
    signal_type_rationale: Optional[str] = None
    # Same underlying fact as signal_type_rationale, in plain language for a
    # non-technical reader - see radar_v2/services/explanations.py's
    # hot_now_clause(), the only consumer. Never invented for a deterministic
    # source's SignalTypeAssignment; those are backfilled with a hand-authored
    # template instead (see signal_route.py) since they never call the LLM.
    signal_type_plain_summary: Optional[str] = None
    signal_type_assigned_by: Optional[str] = None  # deterministic | llm
    # Geography. countries/regions are lists; an empty countries list is a valid
    # answer ("no geographic anchor in the text"), distinct from region_override
    # = "global" ("EU-wide or worldwide scope"). unresolved_countries carries any
    # code that did not roll up to a region, so it is reported rather than lost.
    countries: Optional[list] = None
    regions: Optional[list] = None
    region_override: Optional[str] = None
    geography_confidence: Optional[float] = None
    geography_assigned_by: Optional[str] = None  # deterministic | inferred
    unresolved_countries: Optional[list] = None


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip()).strip()


def build_prompt(
    template: str,
    taxonomy_text: str,
    vertical: str,
    source_name: str,
    title: str,
    summary: Optional[str],
    client_context: Optional[str] = None,
    published_date: Optional[str] = None,
    region_block: str = "",
) -> str:
    client_block = CLIENT_CONTEXT_BLOCK.format(content=client_context) if client_context else ""
    return template.format(
        taxonomy_block=taxonomy_text,
        signal_type_block=build_signal_type_block(),
        signal_type_tie_break=build_tie_break_line(),
        region_block=region_block,
        vertical=vertical,
        source_name=source_name,
        published_date=(published_date or "unknown")[:10],
        title=title or "",
        summary=(summary or "")[:1000],
        client_context_block=client_block,
    )


PLAIN_SUMMARY_REWRITE_PROMPT = (
    "Explain the following sentence as you would to a colleague with no industry background, "
    "in a quick conversation - not a rewrite with fancier synonyms swapped for simpler ones. "
    "Use short, everyday words. Avoid formal or analyst phrasing such as 'concrete', 'named "
    "actor(s)', 'strategic', 'framework', 'entity', 'stakeholder', 'leverage'. Say plainly who "
    "did what, or what changed. Keep exactly the same underlying fact - do not add, remove or "
    "invent any detail. One natural sentence, max 20 words. Return ONLY that sentence, no "
    "quotes, no markdown, no other text.\n\nSentence: {rationale}"
)
MAX_PLAIN_SUMMARY_WORDS = 30  # a soft cap on what gets accepted, not enforced on the model


def rewrite_plain_summary(client: OpenAI, rationale: str, token_counter: Optional[list] = None) -> str:
    """A one-off, cheap rewrite of an already-produced signal_type_rationale
    into plain language - used only to backfill rows classified before
    signal_type_plain_summary existed. Deliberately NOT a call to classify():
    no taxonomy, no article text, no retry-on-invalid-id machinery - just the
    rationale sentence in, a plain sentence out, at a fraction of a full
    classification call's cost."""
    prompt = PLAIN_SUMMARY_REWRITE_PROMPT.format(rationale=rationale)
    raw = _call_with_backoff(client, prompt, token_counter)
    return _strip_fences(raw).strip().strip('"')


def _call_with_backoff(client: OpenAI, prompt: str, token_counter: Optional[list] = None) -> str:
    last_exc = None
    for attempt in range(MAX_TRANSIENT_RETRIES):
        try:
            resp = client.responses.create(
                model=MODEL, input=prompt, temperature=TEMPERATURE,
                reasoning={"effort": REASONING_EFFORT},
            )
            if token_counter is not None and resp.usage:
                token_counter.append(resp.usage.total_tokens)
            return resp.output_text
        except Exception as exc:  # rate limit, timeout, transient 5xx
            last_exc = exc
            wait = min(2 ** attempt, 30)
            time.sleep(wait)
    raise last_exc


def _parse(text: str) -> dict:
    return json.loads(_strip_fences(text))


def _normalize_date(value) -> Optional[str]:
    parsed = parse_date(value)
    return parsed.date().isoformat() if parsed else None


def _signal_type_fields(parsed: dict, published_date: Optional[str]) -> dict:
    """The six signal-type output fields from an already enum-validated
    response. The article's own published_date is a fact we hold; the model's
    signal_date only fills in when we have none."""
    try:
        signal_type_confidence = float(parsed.get("signal_type_confidence"))
    except (TypeError, ValueError):
        signal_type_confidence = 0.0
    event_date = _normalize_date(parsed.get("event_date"))
    return {
        "signal_type": parsed["signal_type"],
        "signal_type_confidence": signal_type_confidence,
        "signal_date": _normalize_date(published_date) or _normalize_date(parsed.get("signal_date")),
        "event_date": event_date,
        "event_date_precision": parsed["event_date_precision"] if event_date else "none",
        "signal_type_rationale": str(parsed.get("signal_type_rationale") or "")[:300],
        "signal_type_plain_summary": str(parsed.get("signal_type_plain_summary") or "")[:300] or None,
    }


def _invalid_country_codes(raw) -> list:
    """Country codes the model returned that are not ISO alpha-2 (or one of the
    EU variants). Enforced with the same retry-on-invalid shape as the taxonomy
    ids: the model is told what it broke rather than having a made-up code
    quietly coerced or dropped."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        return ["<not a list>"]
    invalid = []
    for item in raw:
        code = str(item or "").strip().upper()
        if code not in ISO_ALPHA2 and code not in CODE_ALIASES:
            invalid.append(item)
    return invalid


def _geography_fields(parsed: dict, geography_index) -> dict:
    """The geography output fields from an already enum-validated response,
    rolled up to regions here rather than by the model. An empty countries list
    with no override is a legitimate result and stays empty - it is never
    upgraded to 'global', which is a separate, positive claim."""
    try:
        confidence = float(parsed.get("geography_confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    override = parsed.get("region_override") or ""
    resolution = geography_index.resolve(
        parsed.get("countries") or [],
        region_override=override,
        confidence=confidence,
        assigned_by=INFERRED,
    )
    return {
        "countries": list(resolution.countries),
        "regions": list(resolution.regions),
        "region_override": resolution.region_override or None,
        "geography_confidence": confidence,
        "geography_assigned_by": INFERRED,
        "unresolved_countries": list(resolution.unresolved),
    }


def classify(
    client: OpenAI,
    template: str,
    taxonomy_text: str,
    use_case_ids: set,
    technology_ids: set,
    vertical: str,
    source_name: str,
    title: str,
    summary: Optional[str],
    client_context: Optional[str] = None,
    published_date: Optional[str] = None,
    geography_index=None,
) -> ClassificationResult:
    region_ids = set(geography_index.ids) if geography_index is not None else set()
    region_block = build_region_block(geography_index) if geography_index is not None else ""
    prompt = build_prompt(
        template, taxonomy_text, vertical, source_name, title, summary, client_context,
        published_date, region_block,
    )
    token_counter = []

    parsed = None
    # A response can pass the signal-type enums while failing the taxonomy id
    # check. The two halves are independent judgments, so the last
    # enum-valid signal type is kept rather than being thrown away with the
    # taxonomy half - it passed its own validation, which is not the same as
    # coercing an unparseable one.
    last_valid_signal_type = None
    for attempt in range(MAX_FORMAT_RETRIES + 1):
        raw = _call_with_backoff(client, prompt, token_counter)
        try:
            candidate = _parse(raw)
        except (json.JSONDecodeError, ValueError):
            prompt = prompt + "\n\nYour previous response was not valid JSON. Return ONLY the JSON object, no other text."
            continue

        # Evaluated before the taxonomy check so a response that got the
        # signal type right but an id wrong is still worth salvaging. The
        # enums are enforced below with the same retry-on-invalid shape as the
        # ids - the model gets told what it broke and tries again, rather than
        # having a seventh signal type quietly coerced into a real one.
        signal_type = candidate.get("signal_type")
        precision = candidate.get("event_date_precision")
        signal_type_valid = signal_type in SIGNAL_TYPE_SLUGS and precision in EVENT_DATE_PRECISIONS
        if signal_type_valid:
            last_valid_signal_type = candidate

        uc = candidate.get("use_case_id")
        tech = candidate.get("technology_id")
        if (uc is not None and uc not in use_case_ids) or (tech is not None and tech not in technology_ids):
            prompt = prompt + f"\n\nYour previous response used an id not in the taxonomy ({uc!r}, {tech!r}). Use only the exact ids listed, or null."
            continue
        if signal_type not in SIGNAL_TYPE_SLUGS:
            prompt = prompt + f"\n\nYour previous response used an invalid signal_type ({signal_type!r}). Use exactly one of the six slugs listed."
            continue
        if precision not in EVENT_DATE_PRECISIONS:
            prompt = prompt + f"\n\nYour previous response used an invalid event_date_precision ({precision!r}). Use one of: {', '.join(EVENT_DATE_PRECISIONS)}."
            continue
        if geography_index is not None:
            bad_codes = _invalid_country_codes(candidate.get("countries"))
            if bad_codes:
                prompt = prompt + f"\n\nYour previous response used invalid country codes ({bad_codes!r}). Use only uppercase ISO 3166-1 alpha-2 codes, or an empty array."
                continue
            override = candidate.get("region_override")
            if override and str(override) not in region_ids:
                prompt = prompt + f"\n\nYour previous response used an invalid region_override ({override!r}). Use exactly one of the region ids listed, or null."
                continue

        parsed = candidate
        break

    if parsed is None:
        # Failed record, logged for review - never coerced into a plausible
        # default, which would put an unverified signal type into the horizon.
        salvaged = _signal_type_fields(last_valid_signal_type, published_date) if last_valid_signal_type else {}
        return ClassificationResult(
            use_case_id=None, technology_id=None, confidence=None,
            evidence="parse_error: no valid JSON with taxonomy-valid ids and a valid signal_type after retry",
            status="needs_review",
            total_tokens=sum(token_counter),
            signal_type_rationale=salvaged.get("signal_type_rationale") or "parse_error: signal type not assigned",
            signal_type_assigned_by="llm",
            **{k: v for k, v in salvaged.items() if k != "signal_type_rationale"},
        )

    confidence = parsed.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    use_case_id = parsed.get("use_case_id")
    technology_id = parsed.get("technology_id")
    evidence = str(parsed.get("evidence") or "")
    client_relevance = parsed.get("client_relevance")
    client_relevance_reason = parsed.get("client_relevance_reason")

    if use_case_id is None and technology_id is None:
        status = "no_match"  # legitimate "nothing fits" — low confidence here is expected, not a review case
    elif confidence < CONFIDENCE_THRESHOLD:
        status = "needs_review"
    else:
        status = "classified"

    return ClassificationResult(
        use_case_id=use_case_id,
        technology_id=technology_id,
        confidence=confidence,
        evidence=evidence,
        status=status,
        client_relevance=float(client_relevance) if client_relevance is not None else None,
        client_relevance_reason=client_relevance_reason,
        total_tokens=sum(token_counter),
        signal_type_assigned_by="llm",
        **_signal_type_fields(parsed, published_date),
        **(_geography_fields(parsed, geography_index) if geography_index is not None else {}),
    )
