import csv
import json
from collections import Counter
from datetime import datetime
from html import escape

from V3_simplified.config import (
    FINAL_RADAR_SIZE,
    MAX_DEEP_RESEARCH,
    MAX_TOPICS_PER_DOMAIN,
    OUTPUT_JSON,
    OUTPUT_CSV,
    OUTPUT_HTML,
)

from discovery import (
    generate_opportunity_spaces,
    build_discovery_query,
)

from V3_simplified.research import (
    ResearchBudget,
    tavily_search,
    quick_research,
    deep_research,
    autonomous_gap_queries,
)

from scoring import (
    build_score,
    classify_horizon,
    generate_why_hot,
    recommended_action,
    unique_domains,
)


def assign_source_ids(results):
    for i, result in enumerate(results, start=1):
        result["source_id"] = f"SRC_{i:05d}"
    return results


def shortlist_candidates(opportunities, budget):
    """
    Quick screening stage.
    """
    candidates = []

    print("\n=== DISCOVERY / SCREENING ===")

    for index, opportunity in enumerate(opportunities, start=1):
        print(
            f"[{index}/{len(opportunities)}] "
            f"{opportunity['label']}"
        )

        results = quick_research(
            opportunity,
            budget
        )

        # Simple evidence score.
        unique_urls = len({
            r.get("url")
            for r in results
            if r.get("url")
        })

        market = sum(
            1 for r in results
            if r["signal_type"] == "market_move"
        )

        proof = sum(
            1 for r in results
            if r["signal_type"] == "proof_signal"
        )

        discovery_score = (
            unique_urls * 10
            + market * 10
            + proof * 10
        )

        if discovery_score >= 30:
            opportunity["discovery_score"] = discovery_score
            opportunity["screening_results"] = results
            candidates.append(opportunity)

    candidates.sort(
        key=lambda x: x["discovery_score"],
        reverse=True
    )

    return candidates


def research_candidates(candidates, budget):
    """
    Deep research on the most promising candidates.
    """
    print("\n=== DEEP RESEARCH ===")

    deep_candidates = candidates[:MAX_DEEP_RESEARCH]

    for index, opportunity in enumerate(
        deep_candidates,
        start=1
    ):
        print(
            f"[{index}/{len(deep_candidates)}] "
            f"{opportunity['label']}"
        )

        results = deep_research(
            opportunity,
            budget
        )

        # Combine screening + deep evidence.
        all_results = (
            opportunity.get("screening_results", [])
            + results
        )

        # Deduplicate URLs.
        seen = set()
        unique_results = []

        for result in all_results:
            url = result.get("url")
            key = url or (
                result.get("title"),
                result.get("query")
            )

            if key not in seen:
                seen.add(key)
                unique_results.append(result)

        opportunity["results"] = unique_results

    return deep_candidates


def perform_gap_searches(opportunities, budget):
    """
    First autonomous loop:
    identify missing signal types and search them.
    """
    print("\n=== AUTONOMOUS GAP SEARCH ===")

    for opportunity in opportunities:
        existing = opportunity.get("results", [])

        missing_queries = autonomous_gap_queries(
            opportunity,
            existing
        )

        # Limit autonomous follow-up to 2 queries/opportunity.
        for query in missing_queries[:2]:

            if not budget.can_spend("basic"):
                return

            extra = tavily_search(
                query=query,
                signal_type="autonomous_gap",
                period_name="recent",
                budget=budget,
                depth="basic",
                max_results=3,
            )

            existing.extend(extra)

        opportunity["results"] = existing


def rank_and_diversify(opportunities):
    """
    Score all opportunities, then prevent one domain from
    dominating the final radar.
    """
    domain_counts = Counter()

    for opportunity in opportunities:
        for domain in unique_domains(opportunity):
            domain_counts[domain] += 1

    for opportunity in opportunities:
        opportunity["domains"] = unique_domains(opportunity)
        opportunity["scores"] = build_score(
            opportunity,
            opportunity.get("results", []),
            domain_counts,
        )
        opportunity["horizon"] = classify_horizon(
            opportunity["scores"]["radar_score"]
        )
        opportunity["why_hot"] = generate_why_hot(
            opportunity.get("results", [])
        )
        opportunity["recommended_action"] = recommended_action(
            opportunity["scores"]["radar_score"]
        )

    opportunities.sort(
        key=lambda x: x["scores"]["radar_score"],
        reverse=True
    )

    selected = []
    selected_domain_counts = Counter()

    for opportunity in opportunities:

        if len(selected) >= FINAL_RADAR_SIZE:
            break

        domains = opportunity["domains"]

        if all(
            selected_domain_counts[d] >= MAX_TOPICS_PER_DOMAIN
            for d in domains
        ):
            continue

        selected.append(opportunity)

        for d in domains:
            selected_domain_counts[d] += 1

    return selected


def build_output(opportunities, budget):
    all_sources = []

    for opportunity in opportunities:
        for result in opportunity.get("results", []):
            all_sources.append({
                "opportunity_id": opportunity["id"],
                **result
            })

    all_sources = assign_source_ids(all_sources)

    # Reconnect source IDs inside opportunities.
    source_map = {}
    for source in all_sources:
        key = (
            source["opportunity_id"],
            source.get("url"),
            source.get("title"),
        )
        source_map[key] = source["source_id"]

    for opportunity in opportunities:
        for result in opportunity.get("results", []):
            key = (
                opportunity["id"],
                result.get("url"),
                result.get("title"),
            )
            result["source_id"] = source_map.get(key)

    return {
        "radar": {
            "name": "Orange Business Innovation Radar",
            "generated_at": datetime.now().isoformat(),
            "research_budget": {
                "max_tavily_credits": budget.max_credits,
                "used_tavily_credits": budget.used,
                "remaining_tavily_credits": budget.remaining(),
            },
            "method": (
                "Automatic opportunity generation, quick screening, "
                "deep research, gap search, scoring and diversification."
            ),
        },
        "opportunities": opportunities,
        "sources": all_sources,
    }


def save_json(data):
    with open(
        OUTPUT_JSON,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def save_csv(opportunities):
    fields = [
        "id",
        "label",
        "vertical",
        "use_case",
        "technology",
        "domains",
        "attractiveness",
        "urgency",
        "momentum",
        "radar_score",
        "horizon",
        "why_hot",
        "recommended_action",
    ]

    with open(
        OUTPUT_CSV,
        "w",
        encoding="utf-8",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields
        )

        writer.writeheader()

        for opportunity in opportunities:
            scores = opportunity["scores"]

            writer.writerow({
                "id": opportunity["id"],
                "label": opportunity["label"],
                "vertical": opportunity["vertical"],
                "use_case": opportunity["use_case"],
                "technology": opportunity["technology"],
                "domains": ", ".join(opportunity["domains"]),
                "attractiveness": scores["attractiveness"],
                "urgency": scores["urgency"],
                "momentum": scores["momentum"],
                "radar_score": scores["radar_score"],
                "horizon": opportunity["horizon"],
                "why_hot": opportunity["why_hot"],
                "recommended_action": opportunity["recommended_action"],
            })


def save_html(data):
    opportunities = data["opportunities"]
    radar = data["radar"]

    cards = []

    for opportunity in opportunities:
        scores = opportunity["scores"]

        sources = opportunity.get("results", [])[:5]

        source_html = "".join(
            f"<li><a href='{escape(str(s.get('url') or '#'))}' "
            f"target='_blank'>{escape(str(s.get('title') or 'Source'))}</a> "
            f"({escape(str(s.get('published_date') or 'date unknown'))})</li>"
            for s in sources
        )

        cards.append(
            f"""
            <div class="card">
                <h2>{escape(opportunity['label'])}</h2>
                <p><b>Horizon:</b> {escape(opportunity['horizon'])}</p>

                <div class="scores">
                    <span>Attractiveness: {scores['attractiveness']}</span>
                    <span>Urgency: {scores['urgency']}</span>
                    <span>Momentum: {scores['momentum']}</span>
                    <span>Radar: {scores['radar_score']}</span>
                </div>

                <h3>Why hot?</h3>
                <p>{escape(opportunity['why_hot'])}</p>

                <h3>Recommended action</h3>
                <p>{escape(opportunity['recommended_action'])}</p>

                <h3>Sources</h3>
                <ul>{source_html}</ul>
            </div>
            """
        )

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Orange Business Innovation Radar</title>
<style>
body {{
    font-family: Arial, sans-serif;
    margin: 40px;
    background: #f5f5f5;
    color: #222;
}}
h1 {{ margin-bottom: 5px; }}
.subtitle {{ color: #666; }}
.card {{
    background: white;
    border-radius: 12px;
    padding: 24px;
    margin: 20px 0;
    box-shadow: 0 2px 8px rgba(0,0,0,.08);
}}
.scores {{
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin: 15px 0;
}}
.scores span {{
    background: #eee;
    padding: 8px 12px;
    border-radius: 20px;
}}
a {{ color: #0057b8; }}
</style>
</head>
<body>
<h1>Orange Business Innovation Radar</h1>
<p class="subtitle">
Generated: {escape(radar['generated_at'])}<br>
Tavily credits used: {radar['research_budget']['used_tavily_credits']}
/
{radar['research_budget']['max_tavily_credits']}
</p>

{''.join(cards)}

</body>
</html>
"""

    with open(
        OUTPUT_HTML,
        "w",
        encoding="utf-8"
    ) as f:
        f.write(html)


def main():
    print("=" * 80)
    print("ORANGE BUSINESS INNOVATION RADAR")
    print("=" * 80)

    budget = ResearchBudget()

    # 1. Generate combinations.
    opportunities = generate_opportunity_spaces()

    print(f"\nGenerated combinations: {len(opportunities)}")

    # 2. Cheap screening.
    candidates = shortlist_candidates(
        opportunities,
        budget
    )

    print(f"\nCandidates after screening: {len(candidates)}")

    if not candidates:
        print(
            "\nNo candidates found. "
            "Try increasing MAX_TAVILY_CREDITS."
        )
        return

    # 3. Deep research.
    researched = research_candidates(
        candidates,
        budget
    )

    # 4. Autonomous gap searches.
    perform_gap_searches(
        researched,
        budget
    )

    # 5. Score + diversify.
    final = rank_and_diversify(
        researched
    )

    # 6. Save.
    data = build_output(
        final,
        budget
    )

    save_json(data)
    save_csv(final)
    save_html(data)

    print("\n" + "=" * 80)
    print("FINAL RADAR")
    print("=" * 80)

    for i, opportunity in enumerate(final, start=1):
        scores = opportunity["scores"]

        print(
            f"\n{i}. {opportunity['label']}"
        )

        print(
            f"   Radar score: {scores['radar_score']}"
        )

        print(
            f"   Attractiveness: {scores['attractiveness']}"
        )

        print(
            f"   Urgency: {scores['urgency']}"
        )

        print(
            f"   Momentum: {scores['momentum']}"
        )

        print(
            f"   Horizon: {opportunity['horizon']}"
        )

        print(
            f"   Domains: {', '.join(opportunity['domains'])}"
        )

        print(
            f"   Why hot: {opportunity['why_hot']}"
        )

    print("\n" + "=" * 80)
    print("FILES CREATED")
    print("=" * 80)

    print(OUTPUT_JSON)
    print(OUTPUT_CSV)
    print(OUTPUT_HTML)

    print("\nTavily credits used:", budget.used)
    print("Tavily credits remaining:", budget.remaining())


if __name__ == "__main__":
    main()
