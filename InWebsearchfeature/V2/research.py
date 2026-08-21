import time
from datetime import datetime
from tavily import TavilyClient

from V3_simplified.config import (
    TAVILY_API_KEY,
    SIGNAL_TYPES,
    TIME_HORIZONS,
    DISCOVERY_MAX_RESULTS,
    DEEP_MAX_RESULTS,
    DISCOVERY_SEARCH_DEPTH,
    DEEP_SEARCH_DEPTH,
    SEARCH_CREDIT_COST,
    MAX_TAVILY_CREDITS,
)

client = TavilyClient(api_key=TAVILY_API_KEY)


class ResearchBudget:
    def __init__(self, max_credits=MAX_TAVILY_CREDITS):
        self.max_credits = max_credits
        self.used = 0

    def can_spend(self, depth):
        return self.used + SEARCH_CREDIT_COST[depth] <= self.max_credits

    def spend(self, depth):
        cost = SEARCH_CREDIT_COST[depth]
        if not self.can_spend(depth):
            return False
        self.used += cost
        return True

    def remaining(self):
        return self.max_credits - self.used


def tavily_search(
    query,
    signal_type,
    period_name,
    budget,
    depth="basic",
    max_results=3,
):
    """
    Executes one Tavily search and stores traceable source data.
    """
    if not budget.spend(depth):
        return []

    start_date, end_date = TIME_HORIZONS[period_name]

    params = {
        "query": query,
        "search_depth": depth,
        "max_results": max_results,
        "start_date": start_date,
        "end_date": end_date,
    }

    try:
        response = client.search(**params)
    except Exception as exc:
        print(f"[TAVILY ERROR] {exc}")
        return []

    results = response.get("results", [])
    structured = []

    for result in results:
        structured.append({
            "source_id": None,
            "signal_type": signal_type,
            "period": period_name,
            "query": query,
            "title": result.get("title"),
            "url": result.get("url"),
            "published_date": result.get("published_date"),
            "tavily_score": result.get("score"),
            "content": result.get("content"),
            "retrieved_at": datetime.now().isoformat(),
        })

    time.sleep(0.4)
    return structured


def quick_research(opportunity, budget):
    """
    Cheap screening: a small number of broad searches.
    """
    base = (
        f"{opportunity['vertical']} "
        f"{opportunity['use_case']} "
        f"{opportunity['technology']}"
    )

    results = []

    queries = [
        (
            f"{base} market growth adoption investment",
            "market_move",
        ),
        (
            f"{base} deployment pilot customer case study",
            "proof_signal",
        ),
    ]

    for query, signal_type in queries:
        if not budget.can_spend(DISCOVERY_SEARCH_DEPTH):
            break

        results.extend(
            tavily_search(
                query=query,
                signal_type=signal_type,
                period_name="recent",
                budget=budget,
                depth=DISCOVERY_SEARCH_DEPTH,
                max_results=DISCOVERY_MAX_RESULTS,
            )
        )

    return results


def deep_research(opportunity, budget):
    """
    Expensive research is only performed on shortlisted candidates.
    """
    results = []

    base = (
        f"{opportunity['vertical']} "
        f"{opportunity['use_case']} "
        f"{opportunity['technology']}"
    )

    for signal_type, description in SIGNAL_TYPES.items():

        # Recent signal.
        recent_query = f"{base} {description}"

        if budget.can_spend(DEEP_SEARCH_DEPTH):
            results.extend(
                tavily_search(
                    query=recent_query,
                    signal_type=signal_type,
                    period_name="recent",
                    budget=budget,
                    depth=DEEP_SEARCH_DEPTH,
                    max_results=DEEP_MAX_RESULTS,
                )
            )

        # Historical evidence for trend / maturity / market evolution.
        if signal_type in {
            "trend",
            "market_move",
            "technology_maturity",
        } and budget.can_spend(DEEP_SEARCH_DEPTH):

            historical_query = (
                f"{base} {description} "
                "historical evolution adoption"
            )

            results.extend(
                tavily_search(
                    query=historical_query,
                    signal_type=signal_type,
                    period_name="historical",
                    budget=budget,
                    depth=DEEP_SEARCH_DEPTH,
                    max_results=DEEP_MAX_RESULTS,
                )
            )

        if not budget.can_spend(DEEP_SEARCH_DEPTH):
            break

    # Add targeted quantitative searches.
    numeric_queries = {
        "market_size": f"{base} market size USD billion",
        "growth": f"{base} CAGR growth forecast",
        "investment": f"{base} investment funding million billion",
        "adoption": f"{base} adoption rate percentage enterprises",
    }

    for metric, query in numeric_queries.items():
        if not budget.can_spend(DEEP_SEARCH_DEPTH):
            break

        results.extend(
            tavily_search(
                query=query,
                signal_type=f"numeric_{metric}",
                period_name="recent",
                budget=budget,
                depth=DEEP_SEARCH_DEPTH,
                max_results=DEEP_MAX_RESULTS,
            )
        )

    return results


def autonomous_gap_queries(opportunity, existing_results):
    """
    Produces extra search ideas based on missing signal types.
    This is intentionally rule-based for the first prototype.
    """
    found_types = {
        r.get("signal_type")
        for r in existing_results
    }

    base = (
        f"{opportunity['vertical']} "
        f"{opportunity['use_case']} "
        f"{opportunity['technology']}"
    )

    missing = []
    for signal_type in SIGNAL_TYPES:
        if signal_type not in found_types:
            missing.append(
                f"{base} {SIGNAL_TYPES[signal_type]}"
            )

    return missing
