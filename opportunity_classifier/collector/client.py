import json
import re
import time
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

MODEL = "glm-5.1"
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
) -> str:
    client_block = CLIENT_CONTEXT_BLOCK.format(content=client_context) if client_context else ""
    return template.format(
        taxonomy_block=taxonomy_text,
        vertical=vertical,
        source_name=source_name,
        title=title or "",
        summary=(summary or "")[:1000],
        client_context_block=client_block,
    )


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
) -> ClassificationResult:
    prompt = build_prompt(template, taxonomy_text, vertical, source_name, title, summary, client_context)
    token_counter = []

    parsed = None
    for attempt in range(MAX_FORMAT_RETRIES + 1):
        raw = _call_with_backoff(client, prompt, token_counter)
        try:
            candidate = _parse(raw)
        except (json.JSONDecodeError, ValueError):
            prompt = prompt + "\n\nYour previous response was not valid JSON. Return ONLY the JSON object, no other text."
            continue

        uc = candidate.get("use_case_id")
        tech = candidate.get("technology_id")
        if (uc is not None and uc not in use_case_ids) or (tech is not None and tech not in technology_ids):
            prompt = prompt + f"\n\nYour previous response used an id not in the taxonomy ({uc!r}, {tech!r}). Use only the exact ids listed, or null."
            continue

        parsed = candidate
        break

    if parsed is None:
        return ClassificationResult(
            use_case_id=None, technology_id=None, confidence=None,
            evidence="parse_error: no valid JSON with taxonomy-valid ids after retry",
            status="needs_review",
            total_tokens=sum(token_counter),
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
    )
