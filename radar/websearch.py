from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from radar.ai import AIClient
from radar.company import company_context
from radar.db import active_company, connect, rows, utcnow, web_search_settings


class SearchError(RuntimeError):
    pass


BLOCKED_MARKERS = (
    "please enable cookies", "enable javascript", "site verification", "making sure you're not a bot",
    "access denied", "verify you are human", "captcha", "cookie preferences", "consent required",
)
NOISE_TAGS = ("script", "style", "noscript", "nav", "footer", "header", "form", "svg")


def _date(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _normalize_result(raw: dict, query: str, provider: str, rank: int) -> dict:
    result = {
        "query": query,
        "provider": provider,
        "engine": raw.get("engine") or provider,
        "rank": rank,
        "title": raw.get("title") or "Untitled result",
        "url": raw.get("url") or "",
        "published_at": _date(raw.get("published_date") or raw.get("publishedDate") or raw.get("date")),
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "content": raw.get("content") or raw.get("snippet") or raw.get("raw_content") or "",
        "provider_score": raw.get("score"),
    }
    result["content_status"] = content_status(result["content"])
    result["content_source"] = "search_snippet"
    result["extraction_error"] = ""
    return result


def content_status(content: str) -> str:
    cleaned = " ".join(str(content or "").split())
    lowered = cleaned.lower()
    if any(marker in lowered for marker in BLOCKED_MARKERS):
        return "blocked"
    if len(cleaned) < 80:
        return "thin"
    return "usable"


def extract_readable_html(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()
    selectors = ("article", "main", "[role=main]", ".article", ".content", "#content")
    container = next((soup.select_one(selector) for selector in selectors if soup.select_one(selector)), soup.body or soup)
    text = " ".join(container.get_text(" ", strip=True).split())
    return title, text[:30000]


def enrich_result(result: dict) -> dict:
    if result["content_status"] == "usable":
        return result
    try:
        response = requests.get(
            result["url"], headers={"User-Agent": "Mozilla/5.0 (compatible; Innovation-Radar/0.3)", "Accept": "text/html,application/xhtml+xml"},
            timeout=30, allow_redirects=True,
        )
        if not response.ok:
            result["content_status"] = "blocked"
            result["extraction_error"] = f"Direct fetch returned HTTP {response.status_code}."
            return result
        content_type = response.headers.get("Content-Type", "").lower()
        if "html" not in content_type:
            result["extraction_error"] = f"Direct fetch returned unsupported content type {content_type or 'unknown'}."
            return result
        page_title, text = extract_readable_html(response.text)
        status = content_status(f"{page_title} {text}")
        if status == "usable":
            result["content"] = text
            result["content_status"] = "enriched"
            result["content_source"] = "direct_page"
            result["extraction_error"] = ""
        else:
            result["content_status"] = "blocked" if status == "blocked" else "thin"
            result["extraction_error"] = f"Direct page remained {result['content_status']} after boilerplate removal (title: {page_title or 'unknown'})."
        return result
    except requests.RequestException as error:
        result["extraction_error"] = f"Direct fetch failed: {error}"
        return result


def search_tavily(query: str, max_results: int, api_key: str, depth: str = "basic") -> list[dict]:
    if not api_key:
        raise SearchError("Tavily API key is missing. Add TAVILY_API_KEY to .env or the current Web search session.")
    response = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": api_key, "query": query, "search_depth": depth, "max_results": max_results, "include_raw_content": False},
        timeout=45,
    )
    if not response.ok:
        raise SearchError(f"Tavily returned HTTP {response.status_code}: {response.text[:300]}")
    return [_normalize_result(item, query, "tavily", index) for index, item in enumerate(response.json().get("results", []), 1) if item.get("url")]


def search_searxng(query: str, max_results: int, base_url: str) -> list[dict]:
    if not base_url.startswith(("http://", "https://")):
        raise SearchError("SearXNG URL must start with http:// or https://.")
    response = requests.get(
        f"{base_url.rstrip('/')}/search",
        params={"q": query, "format": "json", "language": "all", "safesearch": 0},
        headers={"Accept": "application/json", "User-Agent": "Innovation-Radar/0.3"},
        timeout=45,
    )
    content_type = response.headers.get("Content-Type", "").lower()
    if not response.ok:
        detail = response.text[:300].strip() or "empty response"
        if response.status_code in {403, 429, 503}:
            raise SearchError(f"SearXNG instance is unavailable, rate-limited, or blocking API clients (HTTP {response.status_code}; {detail}). Choose another public instance or use local/Tavily mode.")
        if response.status_code == 404:
            raise SearchError("SearXNG JSON endpoint was not found (HTTP 404). `searx.space` is an instance directory, not a search endpoint; choose an instance URL listed there.")
        raise SearchError(f"SearXNG returned HTTP {response.status_code}: {detail}")
    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError as error:
        preview = response.text[:160].replace("\n", " ")
        raise SearchError(f"This URL returned {content_type or 'non-JSON content'} instead of SearXNG JSON. The public instance may disable `format=json`, show a bot challenge, or redirect to HTML. Response preview: {preview!r}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("results", []), list):
        raise SearchError("SearXNG returned JSON but not the expected object with a `results` array.")
    return [_normalize_result(item, query, "searxng", index) for index, item in enumerate(payload.get("results", [])[:max_results], 1) if item.get("url")]


def test_searxng_instance(base_url: str) -> dict:
    results = search_searxng("SearXNG compatibility test", 1, base_url)
    return {"compatible": True, "result_count": len(results), "sample_url": results[0]["url"] if results else "", "dates_supported_in_sample": bool(results and results[0]["published_at"])}


def execute_search(query: str, max_results: int, session_tavily_key: str = "") -> list[dict]:
    settings = web_search_settings()
    if settings["provider"] == "tavily":
        return search_tavily(query, max_results, session_tavily_key or os.getenv("TAVILY_API_KEY", ""), settings["tavily_depth"])
    url = settings["public_searxng_url"] if settings["provider"] == "searxng_public" else settings["searxng_url"]
    if not url:
        raise SearchError("No public SearXNG instance URL is configured. `https://searx.space/` lists instances but is not itself a search endpoint.")
    return search_searxng(query, max_results, url)


def persist_search(purpose: str, queries: list[str], max_results: int, session_tavily_key: str = "", opportunity_id: int | None = None) -> dict:
    settings = web_search_settings()
    with connect() as connection:
        run_id = connection.execute(
            "INSERT INTO web_search_runs(purpose,provider,opportunity_id,started_at,status) VALUES(?,?,?,?,?)",
            (purpose, settings["provider"], opportunity_id, utcnow(), "running"),
        ).lastrowid
    all_results = []
    try:
        for query in queries[:settings["max_queries"]]:
            all_results.extend(execute_search(query, max_results, session_tavily_key))
        deduplicated = {}
        for result in all_results:
            deduplicated.setdefault(result["url"].split("#", 1)[0], result)
        enriched_results = [enrich_result(result) for result in deduplicated.values()]
        with connect() as connection:
            for result in enriched_results:
                connection.execute(
                    """INSERT OR IGNORE INTO web_search_results(run_id,query,provider,engine,rank,title,url,published_at,retrieved_at,content,provider_score,content_status,content_source,extraction_error)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (run_id, result["query"], result["provider"], result["engine"], result["rank"], result["title"], result["url"], result["published_at"], result["retrieved_at"], result["content"][:12000], result["provider_score"], result["content_status"], result["content_source"], result["extraction_error"]),
                )
            connection.execute("UPDATE web_search_runs SET finished_at=?,status='completed',query_count=?,result_count=? WHERE id=?", (utcnow(), len(queries[:settings["max_queries"]]), len(enriched_results), run_id))
        return {"run_id": run_id, "queries": queries[:settings["max_queries"]], "results": enriched_results}
    except Exception as error:
        with connect() as connection:
            connection.execute("UPDATE web_search_runs SET finished_at=?,status='failed',error=? WHERE id=?", (utcnow(), str(error)[:1000], run_id))
        raise


def import_search_results(run_id: int) -> dict:
    results = rows("SELECT * FROM web_search_results WHERE run_id=? ORDER BY id", (run_id,))
    usable = [result for result in results if result.get("content_status") in {"usable", "enriched"}]
    added = 0
    with connect() as connection:
        source_name = f"Web search run {run_id}"
        source_url = f"websearch://run/{run_id}"
        connection.execute("INSERT OR IGNORE INTO sources(name,url,domain,geography,enabled) VALUES(?,?,?,?,0)", (source_name, source_url, "Web search", "Global"))
        source_id = connection.execute("SELECT id FROM sources WHERE url=?", (source_url,)).fetchone()[0]
        for result in usable:
            guid = hashlib.sha256(result["url"].encode("utf-8")).hexdigest()
            before = connection.total_changes
            connection.execute(
                "INSERT OR IGNORE INTO articles(source_id,guid,title,url,published_at,content,fetched_at) VALUES(?,?,?,?,?,?,?)",
                (source_id, guid, result["title"], result["url"], result["published_at"], result["content"][:12000], result["retrieved_at"]),
            )
            if connection.total_changes > before:
                article_id = connection.execute("SELECT id FROM articles WHERE guid=?", (guid,)).fetchone()[0]
                connection.execute("UPDATE web_search_results SET article_id=? WHERE id=?", (article_id, result["id"]))
                added += 1
    return {"run_id": run_id, "results": len(results), "usable_results": len(usable), "skipped_unusable": len(results) - len(usable), "articles_added": added}


def enrich_search_run(run_id: int) -> dict:
    stored = rows("SELECT * FROM web_search_results WHERE run_id=? ORDER BY id", (run_id,))
    enriched = blocked = thin = usable = 0
    for row in stored:
        result = dict(row)
        result["content_status"] = content_status(result.get("content", ""))
        result["content_source"] = result.get("content_source") or "search_snippet"
        result["extraction_error"] = result.get("extraction_error") or ""
        result = enrich_result(result)
        with connect() as connection:
            connection.execute(
                "UPDATE web_search_results SET content=?,content_status=?,content_source=?,extraction_error=? WHERE id=?",
                (result["content"][:12000], result["content_status"], result["content_source"], result["extraction_error"], result["id"]),
            )
        enriched += result["content_status"] == "enriched"
        blocked += result["content_status"] == "blocked"
        thin += result["content_status"] == "thin"
        usable += result["content_status"] == "usable"
    return {"results": len(stored), "enriched": enriched, "usable": usable, "blocked": blocked, "thin": thin}


def _opportunity(opportunity_id: int) -> dict:
    result = rows("SELECT * FROM opportunities WHERE id=?", (opportunity_id,))
    if not result:
        raise SearchError("Opportunity not found.")
    return result[0]


def normalize_research_plan(planning: dict, maximum: int) -> list[dict]:
    raw_tasks = planning.get("research_tasks") or planning.get("queries") or []
    tasks = []
    seen = set()
    for index, raw in enumerate(raw_tasks):
        item = {"query": raw} if isinstance(raw, str) else raw if isinstance(raw, dict) else {}
        query = " ".join(str(item.get("query", "")).split()).strip()
        fingerprint = query.casefold()
        if not query or fingerprint in seen:
            continue
        seen.add(fingerprint)
        tasks.append({
            "purpose": str(item.get("purpose") or f"Research question {index + 1}"),
            "unknown": str(item.get("unknown") or "Evidence gap to resolve"),
            "query": query[:300],
            "preferred_source_types": item.get("preferred_source_types") if isinstance(item.get("preferred_source_types"), list) else [],
            "geography": str(item.get("geography") or "Belgium / Europe / Global as relevant"),
            "freshness": str(item.get("freshness") or "recent unless historical comparison is required"),
            "decision_use": str(item.get("decision_use") or "Improve the opportunity decision"),
        })
        if len(tasks) >= maximum:
            break
    return tasks


def ensure_plan_coverage(tasks: list[dict], opportunity: dict, company_name: str, maximum: int) -> tuple[list[dict], dict]:
    dimensions = {
        "market_demand": ("market demand", "Buyer demand or procurement evidence", f"{opportunity['use_case']} {opportunity['vertical']} buyer demand procurement Europe"),
        "financial_quantification": ("financial quantitative", "Market/ROI quantification", f"{opportunity['use_case']} market size adoption ROI benchmark Europe"),
        "regulation_risk": ("regulation risk compliance", "Regulatory trigger and risk", f"{opportunity['vertical']} {opportunity['use_case']} regulation compliance Belgium Europe"),
        "implementation_proof": ("implementation proof deployment case study", "Named implementation proof", f"{opportunity['technology']} {opportunity['use_case']} named deployment case study results"),
        "company_ecosystem": ("company competitor partner capability", "Company and ecosystem fit", f"{company_name} {opportunity['technology']} partners competitors capabilities"),
    }
    searchable = lambda task: f"{task.get('purpose','')} {task.get('unknown','')} {task.get('query','')}".casefold()
    coverage = {}
    output = list(tasks)
    for dimension, (keywords, purpose, fallback_query) in dimensions.items():
        keyword_set = keywords.split()
        covered = any(any(keyword in searchable(task) for keyword in keyword_set) for task in output)
        coverage[dimension] = covered
        if not covered and len(output) < maximum:
            output.append(normalize_research_plan({"research_tasks": [{"purpose": purpose, "unknown": purpose, "query": fallback_query, "preferred_source_types": ["primary source", "official statistics", "named customer evidence"], "decision_use": f"Resolve {dimension.replace('_', ' ')} for the report"}]}, 1)[0])
            coverage[dimension] = True
    return output[:maximum], coverage


def build_research_plan(opportunity: dict, evidence: list[dict], client: AIClient, maximum: int) -> dict:
    factors = json.loads(opportunity.get("factors_json") or "{}")
    current_domains = sorted({urlsplit(item.get("source_url", "")).netloc for item in evidence if item.get("source_url")})
    planner_system = """You are a senior market-research planner. Analyze the opportunity before searching. Return JSON with opportunity_interpretation, decision_questions (array), known_evidence (array), evidence_gaps (array), naming_risks (array), and research_tasks (array). Each research task must contain purpose, unknown, query, preferred_source_types (array), geography, freshness, and decision_use. Queries must be natural search-engine queries, concise, varied, and independently useful. Do not repeat the full opportunity title in every query. Translate internal or invented opportunity wording into terminology likely used by buyers, regulators, analysts, technical teams, competitors, and procurement portals. Separate market demand, quantitative/financial evidence, regulation, implementation proof, competitor/partner landscape, and company fit when those gaps matter. Prefer primary sources for law, procurement, financials, and named deployments. Do not assume the current opportunity name is correct."""
    planner_input = f"""Create at most {maximum} prioritized research tasks.

OPPORTUNITY RECORD:
{json.dumps(opportunity, ensure_ascii=False)}

CURRENT SCORE FACTORS AND RATIONALES:
{json.dumps(factors, ensure_ascii=False)}

EXISTING EVIDENCE:
{json.dumps(evidence, ensure_ascii=False)}

CURRENT EVIDENCE DOMAINS:
{json.dumps(current_domains, ensure_ascii=False)}

ACTIVE COMPANY:
{json.dumps(active_company(), ensure_ascii=False)}

BOUNDED COMPANY CONTEXT FOR REPORT PLANNING:
{company_context(6000, 'full_report', 5)}"""
    planning = client.generate_json(planner_system, planner_input)
    tasks = normalize_research_plan(planning, maximum)
    tasks, coverage = ensure_plan_coverage(tasks, opportunity, active_company().get("name", "the company"), maximum)
    return {
        "opportunity_interpretation": planning.get("opportunity_interpretation", ""),
        "decision_questions": planning.get("decision_questions", []),
        "known_evidence": planning.get("known_evidence", []),
        "evidence_gaps": planning.get("evidence_gaps", []),
        "naming_risks": planning.get("naming_risks", []),
        "research_tasks": tasks,
        "coverage": coverage,
    }


def generate_opportunity_report(opportunity_id: int, client: AIClient, session_tavily_key: str = "") -> dict:
    opportunity = _opportunity(opportunity_id)
    settings = web_search_settings()
    evidence = rows("SELECT source_name,source_url,published_at,signal_type,claim FROM evidence WHERE opportunity_id=?", (opportunity_id,))
    research_plan = build_research_plan(opportunity, evidence, client, settings["max_queries"])
    if not research_plan["research_tasks"]:
        research_plan["research_tasks"] = normalize_research_plan({"queries": [
            f"{opportunity['use_case']} {opportunity['vertical']} buyer demand Europe",
            f"{opportunity['technology']} named deployment ROI case study",
            f"{opportunity['vertical']} {opportunity['use_case']} regulation procurement Belgium",
        ]}, settings["max_queries"])
    queries = [task["query"] for task in research_plan["research_tasks"]]
    search = persist_search("opportunity_report", queries, settings["max_results_per_query"], session_tavily_key, opportunity_id)
    source_rows = [{"source_id": index, **item} for index, item in enumerate((item for item in search["results"] if item.get("content_status") in {"usable", "enriched"}), 1)]
    if not source_rows:
        raise SearchError("Search returned no usable content after cookie/challenge cleanup. Try another provider, query, or source instance.")
    report_prompt = """Create a decision-ready opportunity report using only the supplied opportunity, research plan, existing evidence, company guidance, and numbered web sources. Return JSON with: executive_summary; confidence_and_gaps; market_estimates array (metric, low, base, high, unit, period, assumption, source_ids); company_fit (direct_role, partner_role, capability_gaps); competitors_and_partners array; risks array (risk, likelihood 1-5, impact 1-5, mitigation, source_ids); roadmap array (phase, timing, action, owner_type, success_metric); financial_scenarios array (scenario, investment_low, investment_high, value_low, value_high, currency, horizon, assumptions, source_ids); recommendation; next_validation_steps array. Estimates must be ranges, identify assumptions, and cite source_ids. Explain when the search failed to answer a planned question. Never present a search snippet as verified fact."""
    payload = client.generate_json(
        report_prompt,
        f"OPPORTUNITY:\n{json.dumps(opportunity, ensure_ascii=False)}\n\nRESEARCH PLAN:\n{json.dumps(research_plan, ensure_ascii=False)}\n\nEXISTING EVIDENCE:\n{json.dumps(evidence, ensure_ascii=False)}\n\nCOMPANY CONTEXT FOR FULL REPORT:\n{company_context(8000, 'full_report', 5)}\n\nWEB SOURCES:\n{json.dumps(source_rows, ensure_ascii=False)[:70000]}",
    )
    payload["research_plan"] = research_plan
    payload["sources"] = source_rows
    with connect() as connection:
        report_id = connection.execute(
            """INSERT INTO opportunity_reports(opportunity_id,company_name,status,created_at,model,search_provider,search_run_id,query_count,source_count,report_json)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (opportunity_id, active_company().get("name", ""), "completed", utcnow(), client.model, settings["provider"], search["run_id"], len(queries), len(source_rows), json.dumps(payload, ensure_ascii=False)),
        ).lastrowid
    return {"report_id": report_id, "search_run_id": search["run_id"], "report": payload, "api_requests": client.request_count}
