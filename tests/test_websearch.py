from radar.websearch import _normalize_result, content_status, enrich_result, ensure_plan_coverage, extract_readable_html, normalize_research_plan, search_searxng
from radar.display import table_safe


class FakeResponse:
    ok = True
    headers = {"Content-Type": "application/json"}

    def json(self):
        return {"results": [{"title": "Result", "url": "https://example.com/a", "content": "Evidence", "publishedDate": "2026-08-20", "engine": "bing"}]}


def test_searxng_keeps_url_date_engine_and_query(monkeypatch):
    monkeypatch.setattr("radar.websearch.requests.get", lambda *args, **kwargs: FakeResponse())
    result = search_searxng("industrial AI", 5, "http://localhost:8888")[0]
    assert result["url"] == "https://example.com/a"
    assert result["published_at"] == "2026-08-20"
    assert result["engine"] == "bing"
    assert result["query"] == "industrial AI"


def test_normalizer_keeps_missing_date_blank():
    result = _normalize_result({"title": "No date", "url": "https://example.com"}, "query", "searxng", 1)
    assert result["published_at"] == ""


def test_cookie_and_bot_snippets_are_blocked():
    assert content_status("Please Enable Cookies to continue") == "blocked"
    assert content_status("Making sure you're not a bot!") == "blocked"


def test_readable_html_removes_navigation_and_scripts():
    title, text = extract_readable_html("<html><head><title>Article</title><script>noise</script></head><body><nav>Menu</nav><main><h1>Finding</h1><p>" + "Evidence " * 20 + "</p></main></body></html>")
    assert title == "Article"
    assert "Finding" in text
    assert "Menu" not in text
    assert "noise" not in text


class BlockedPage:
    ok = True
    status_code = 200
    headers = {"Content-Type": "text/html"}
    text = "<html><head><title>Site verification</title></head><body>Please Enable Cookies</body></html>"


def test_unresolved_cookie_page_stays_blocked(monkeypatch):
    monkeypatch.setattr("radar.websearch.requests.get", lambda *args, **kwargs: BlockedPage())
    result = _normalize_result({"title": "Financials", "url": "https://example.com", "content": "Please Enable Cookies"}, "query", "searxng", 1)
    enriched = enrich_result(result)
    assert enriched["content_status"] == "blocked"
    assert "remained blocked" in enriched["extraction_error"]


def test_table_safe_serializes_mixed_citation_ids():
    cleaned = table_safe([{"risk": "Example", "source_ids": [1, "E2"]}, {"risk": "Other", "source_ids": [2]}])
    assert cleaned[0]["source_ids"] == '[1, "E2"]'
    assert cleaned[1]["source_ids"] == "[2]"


def test_research_plan_deduplicates_and_keeps_task_purpose():
    plan = normalize_research_plan({"research_tasks": [
        {"purpose": "Demand", "unknown": "Buyer need", "query": "bank threat visibility buyer survey", "preferred_source_types": ["customer survey"]},
        {"purpose": "Duplicate", "query": "  bank threat visibility buyer survey  "},
        {"purpose": "Regulation", "query": "DORA network monitoring requirements banks"},
    ]}, 5)
    assert len(plan) == 2
    assert plan[0]["purpose"] == "Demand"
    assert plan[1]["query"] == "DORA network monitoring requirements banks"


def test_research_plan_fills_missing_dimensions_within_budget():
    opportunity = {"vertical": "Banking", "use_case": "threat visibility", "technology": "network analytics"}
    tasks = normalize_research_plan({"queries": ["bank threat visibility buyer demand"]}, 5)
    completed, coverage = ensure_plan_coverage(tasks, opportunity, "Orange Business", 5)
    assert len(completed) == 5
    assert coverage["market_demand"] is True
    assert coverage["financial_quantification"] is True
    assert coverage["implementation_proof"] is True
