import json
import os
import random
import re

import requests

from connectors.base import make_signal

NAVY_ENDPOINT = "https://api.navy/v1/chat/completions"
DEFAULT_MODEL = "sonar"  # cheapest Sonar tier, built-in live web search
SAMPLE_SEED = 42  # fixed seed so a given --sample-fraction is reproducible run to run

SYSTEM_PROMPT = (
    "You are a research assistant with real-time web search access. "
    "For the given query, search the web and return the most relevant, "
    "recent results as a JSON array. Each item must have exactly these "
    'keys: "title", "url", "published_date" (YYYY-MM-DD or null), '
    '"snippet" (1-2 sentences). Return ONLY the JSON array, no markdown '
    "fences, no other text. If you find nothing relevant, return []."
)

JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def build_queries(matrix, cells, boosted_cells):
    templates = matrix["query_templates"]
    queries = []
    for vertical, domain in cells:
        v_kw = matrix["verticals"][vertical]["keywords"]
        d_kw = matrix["domains"][domain]["keywords"]
        boosted = (vertical, domain) in boosted_cells
        for signal_type, template in templates.items():
            queries.append({
                "vertical": vertical,
                "domain": domain,
                "signal_type": signal_type,
                "query": template.format(v=v_kw, d=d_kw),
                "boosted": boosted,
            })
    return queries


def sample_queries(queries, sample_fraction):
    if sample_fraction >= 1.0:
        return queries
    k = max(1, round(len(queries) * sample_fraction))
    return random.Random(SAMPLE_SEED).sample(queries, k)


def parse_results(raw_text):
    match = JSON_ARRAY_RE.search(raw_text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def search(query, lookback_days, api_key, model):
    prompt = (
        f"{query}\n\n"
        f"Only include results published in the last {lookback_days} days "
        "if possible. Prioritize regulators, official announcements, "
        "analyst reports, procurement notices, and credible trade press "
        "over generic blog content."
    )
    response = requests.post(
        NAVY_ENDPOINT,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        },
        timeout=60,
    )
    response.raise_for_status()
    body = response.json()
    content = body["choices"][0]["message"]["content"]
    usage = body.get("usage") or {}
    return parse_results(content), usage


def collect(matrix, cells, boosted_cells, model=DEFAULT_MODEL, sample_fraction=1.0):
    api_key = os.environ.get("NAVY_API_KEY")
    if not api_key:
        print("[navy] NAVY_API_KEY not set, skipping search connector")
        return []

    cfg = matrix["search"]
    signals = []
    full_queries = build_queries(matrix, cells, boosted_cells)
    queries = sample_queries(full_queries, sample_fraction)
    if sample_fraction < 1.0:
        print(f"[navy] TEST MODE: sample_fraction={sample_fraction} "
              f"-> running {len(queries)}/{len(full_queries)} queries")

    usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    queries_run = 0
    for q in queries:
        try:
            results, usage = search(q["query"], cfg["lookback_days"], api_key, model)
        except (requests.RequestException, KeyError, IndexError) as exc:
            print(f"[navy] query failed ({q['vertical']} x {q['domain']}): {exc}")
            continue
        queries_run += 1
        for key in usage_totals:
            usage_totals[key] += usage.get(key, 0) or 0
        for r in results:
            if not isinstance(r, dict) or not r.get("title") or not r.get("url"):
                continue
            signals.append(make_signal(
                connector="navy",
                source_name=r["url"].split("/")[2] if "/" in r["url"] else "navy",
                source_type="web_search",
                title=r["title"],
                url=r["url"],
                published_at=r.get("published_date"),
                content=r.get("snippet"),
                vertical_hint=q["vertical"],
                domain_hint=q["domain"],
                signal_type_hint=q["signal_type"],
                extra={"model": model, "query": q["query"]},
            ))
        print(f"[navy] {q['vertical']} x {q['domain']} ({q['signal_type']}): "
              f"{len(results)} results, {usage.get('total_tokens', 0)} tokens")

    print(f"\n[navy] Token usage over {queries_run} queries — "
          f"prompt: {usage_totals['prompt_tokens']}, "
          f"completion: {usage_totals['completion_tokens']}, "
          f"total: {usage_totals['total_tokens']}")
    if queries_run:
        avg_tokens = usage_totals["total_tokens"] / queries_run
        print(f"[navy] Average: {avg_tokens:.0f} tokens/query")
        if sample_fraction < 1.0:
            projected = avg_tokens * len(full_queries)
            print(f"[navy] Projected full run ({len(full_queries)} queries): "
                  f"~{projected:.0f} tokens total "
                  f"(scale sample_fraction up/down and re-check against your "
                  f"daily quota before running the full matrix)")

    return signals
