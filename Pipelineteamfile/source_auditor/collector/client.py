import json
import os
import re
import time
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

from common.trust import AUTO_ASSIGNABLE_SLUGS, DEFAULT_UNKNOWN_CATEGORY

MODEL = os.environ.get("NAVY_MODEL", "glm-5.1")  # same env-driven pattern as opportunity_classifier
TEMPERATURE = 0.1  # same as the classifier - determinism over creativity for a factual categorization
REASONING_EFFORT = "none"  # no measured quality gain for the classifier at default effort; same call shape here
MAX_FORMAT_RETRIES = 2
MAX_TRANSIENT_RETRIES = 6

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def make_client(api_key: str, base_url: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=base_url)


@dataclass
class AuditResult:
    category: str
    evidence: str
    confidence: Optional[float]
    error: Optional[str] = None
    total_tokens: int = 0


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip()).strip()


def build_categories_block(categories: list) -> str:
    return "\n".join(f"- {c['slug']}: {c['description']}" for c in categories if c["auto_assignable"])


def build_prompt(template: str, source_name: str, source_type: str, example_titles: list, categories_block: str) -> str:
    titles_text = "; ".join(example_titles[:5]) if example_titles else "(none available)"
    return template.format(
        source_name=source_name,
        source_type=source_type,
        example_titles=titles_text,
        categories_block=categories_block,
    )


def _call_with_backoff(client: OpenAI, prompt: str, token_counter: list) -> str:
    last_exc = None
    for attempt in range(MAX_TRANSIENT_RETRIES):
        try:
            resp = client.responses.create(
                model=MODEL, input=prompt, temperature=TEMPERATURE,
                reasoning={"effort": REASONING_EFFORT},
            )
            if resp.usage:
                token_counter.append(resp.usage.total_tokens)
            return resp.output_text
        except Exception as exc:  # rate limit, timeout, transient 5xx
            last_exc = exc
            wait = min(2 ** attempt, 30)
            time.sleep(wait)
    raise last_exc


def _parse(text: str) -> dict:
    return json.loads(_strip_fences(text))


def audit(client: OpenAI, template: str, categories_block: str,
          source_name: str, source_type: str, example_titles: list) -> AuditResult:
    prompt = build_prompt(template, source_name, source_type, example_titles, categories_block)
    token_counter = []

    parsed = None
    for attempt in range(MAX_FORMAT_RETRIES + 1):
        raw = _call_with_backoff(client, prompt, token_counter)
        try:
            candidate = _parse(raw)
        except (json.JSONDecodeError, ValueError):
            prompt = prompt + "\n\nYour previous response was not valid JSON. Return ONLY the JSON object, no other text."
            continue

        category = candidate.get("category")
        if category not in AUTO_ASSIGNABLE_SLUGS:
            prompt = prompt + f"\n\nYour previous response used an invalid category ({category!r}). Use only one of the exact slugs listed."
            continue

        parsed = candidate
        break

    if parsed is None:
        # Conservative on failure, same principle as an unrecognized source:
        # never guess a higher category when the model can't even follow format.
        return AuditResult(
            category=DEFAULT_UNKNOWN_CATEGORY,
            evidence="",
            confidence=0.0,
            error="parse_error: no valid category after retry",
            total_tokens=sum(token_counter),
        )

    evidence = str(parsed.get("evidence") or "")
    try:
        confidence = float(parsed.get("confidence"))
    except (TypeError, ValueError):
        confidence = None

    return AuditResult(
        category=parsed["category"],
        evidence=evidence,
        confidence=confidence,
        total_tokens=sum(token_counter),
    )
