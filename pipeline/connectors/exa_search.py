import os
from datetime import datetime, timedelta, timezone

import requests

from connectors.base import make_signal

EXA_ENDPOINT = "https://api.exa.ai/search"


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


def search(query, num_results, lookback_days, api_key):
    start_date = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    response = requests.post(
        EXA_ENDPOINT,
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        json={
            "query": query,
            "numResults": num_results,
            "startPublishedDate": start_date,
            "contents": {"text": {"maxCharacters": 4000}},
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("results", [])


def collect(matrix, cells, boosted_cells):
    api_key = os.environ.get("EXA_API_KEY")
    if not api_key:
        print("[exa] EXA_API_KEY not set, skipping search connector")
        return []

    cfg = matrix["search"]
    signals = []
    queries = build_queries(matrix, cells, boosted_cells)
    for q in queries:
        multiplier = 2 if q["boosted"] else 1
        try:
            results = search(
                q["query"],
                cfg["results_per_query"] * multiplier,
                cfg["lookback_days"],
                api_key,
            )
        except requests.RequestException as exc:
            print(f"[exa] query failed ({q['vertical']} x {q['domain']}): {exc}")
            continue
        for r in results:
            signals.append(make_signal(
                connector="exa",
                source_name=r.get("url", "").split("/")[2] if r.get("url") else "exa",
                source_type="web_search",
                title=r.get("title") or "",
                url=r.get("url"),
                published_at=r.get("publishedDate"),
                content=r.get("text"),
                vertical_hint=q["vertical"],
                domain_hint=q["domain"],
                signal_type_hint=q["signal_type"],
                extra={"exa_score": r.get("score"), "query": q["query"]},
            ))
        print(f"[exa] {q['vertical']} x {q['domain']} ({q['signal_type']}): {len(results)} results")
    return [s for s in signals if s["title"]]
