from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests
from openai import OpenAI

from radar_v2.services import extension_store, team_repository


def _ai(base_url: str, api_key: str, model: str, mode: str):
    if not api_key:
        raise ValueError("Add an intelligence provider key in Settings before creating a report")
    return OpenAI(api_key=api_key, base_url=base_url.rstrip("/")), mode


def _json_call(client: OpenAI, model: str, mode: str, instruction: str, prompt: str) -> dict:
    if mode == "chat":
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": instruction}, {"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
    else:
        raw = client.responses.create(model=model, instructions=instruction, input=prompt).output_text
    return json.loads(raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())


def _search(query: str, settings: dict) -> list[dict]:
    if settings["search_provider"] == "tavily":
        key = os.getenv("TAVILY_API_KEY", "")
        if not key:
            raise ValueError("Tavily is selected but TAVILY_API_KEY is not configured")
        response = requests.post("https://api.tavily.com/search", json={"api_key": key, "query": query, "search_depth": settings["tavily_depth"], "max_results": settings["max_search_results"]}, timeout=45)
        response.raise_for_status()
        items = response.json().get("results", [])
        return [{"title": item.get("title", "Untitled"), "url": item.get("url", ""), "source": "Tavily", "date": item.get("published_date", "") or "Recent", "excerpt": item.get("content", "")} for item in items if item.get("url")]
    response = requests.get(f"{settings['searxng_url'].rstrip('/')}/search", params={"q": query, "format": "json", "language": "all"}, headers={"Accept": "application/json", "User-Agent": "Innovation-Radar-V2/1.0"}, timeout=45)
    response.raise_for_status()
    items = response.json().get("results", [])
    return [{"title": item.get("title", "Untitled"), "url": item.get("url", ""), "source": item.get("engine", "SearXNG"), "date": item.get("publishedDate", "") or "Recent", "excerpt": item.get("content", "")} for item in items if item.get("url")]


def create_focused_report(opportunity_id: int, api_key: str, progress=None) -> tuple[int, dict]:
    settings = extension_store.settings()
    client, mode = _ai(settings["ai_base_url"], api_key, settings["ai_model"], settings["ai_mode"])
    opportunity, evidence = team_repository.opportunity_detail(opportunity_id)
    if progress:
        progress("Reading the selected opportunity and existing evidence")
    plan = _json_call(
        client, settings["ai_model"], mode,
        "You are a senior research planner. Return JSON with a concise queries array. Create varied searches for demand, financial scale/ROI, regulation and risks, implementation proof, and company/competitor/partner fit. Use natural buyer terminology instead of repeating an internal opportunity title.",
        f"Opportunity: {json.dumps(opportunity)}\nExisting evidence: {json.dumps(evidence)}\nCompany: {json.dumps(extension_store.active_company())}\nCreate at most {settings['max_research_queries']} queries.",
    )
    queries = [str(query).strip() for query in plan.get("queries", []) if str(query).strip()][:settings["max_research_queries"]]
    if progress:
        progress(f"Running {len(queries)} focused research searches")
    results = []
    for query in queries:
        results.extend(_search(query, settings))
    unique = {}
    for result in results:
        unique.setdefault(result["url"].split("#", 1)[0], result)
    sources = list(unique.values())[:50]
    if progress:
        progress(f"Synthesising {len(sources)} retained sources into a decision report")
    report = _json_call(
        client, settings["ai_model"], mode,
        "Create a concise, decision-ready opportunity report using only the supplied evidence and numbered web sources. Return JSON with executive_summary, market_signal, financial_indicators, company_fit, competitor_partner_landscape, risks (array of risk, likelihood, impact, mitigation), roadmap (array of phase, action, success_metric), recommendation, gaps, and source_ids. Keep estimates as ranges with assumptions. Never invent facts.",
        f"Opportunity: {json.dumps(opportunity)}\nExisting evidence: {json.dumps(evidence)}\nResearch plan: {json.dumps(plan)}\nWeb sources: {json.dumps([{**item, 'source_id': index + 1} for index, item in enumerate(sources)])[:70000]}",
    )
    report["queries"] = queries
    report["sources"] = [{**item, "source_id": index + 1} for index, item in enumerate(sources)]
    report["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report_id = extension_store.save_focused_report(opportunity_id, f"{opportunity['use_case']} business case", report, len(sources))
    return report_id, report
