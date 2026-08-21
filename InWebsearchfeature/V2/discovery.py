from itertools import product
from V3_simplified.config import VERTICALS, USE_CASES, TECHNOLOGIES, MAX_CANDIDATES


def generate_opportunity_spaces():
    """
    Generates Vertical × Use Case × Technology combinations.

    We deliberately sample rather than research every possible
    combination. The research stage will decide which candidates
    deserve deeper investigation.
    """
    opportunities = []

    for vertical, use_case, technology in product(
        VERTICALS, USE_CASES, TECHNOLOGIES
    ):
        opportunities.append({
            "id": f"OPP_{len(opportunities)+1:04d}",
            "vertical": vertical,
            "use_case": use_case,
            "technology": technology,
            "label": f"{vertical} × {use_case} × {technology}",
        })

    # Deterministic spread across the matrix.
    if len(opportunities) <= MAX_CANDIDATES:
        return opportunities

    step = len(opportunities) / MAX_CANDIDATES
    selected = []
    index = 0.0

    while len(selected) < MAX_CANDIDATES:
        selected.append(opportunities[int(index)])
        index += step

    return selected


def build_discovery_query(opportunity):
    return (
        f"{opportunity['vertical']} "
        f"{opportunity['use_case']} "
        f"{opportunity['technology']} "
        "business opportunity market growth adoption investment"
    )


def build_autonomous_opportunity_queries(vertical=None):
    """
    Searches for opportunities without predefining the full
    Vertical × Use Case × Technology combination.
    """
    scope = vertical or "B2B industry"

    return [
        f"{scope} emerging digital business opportunities 2026",
        f"{scope} emerging technology use cases enterprise growth",
        f"{scope} digital transformation investment trends 2025 2026",
        f"{scope} new technology adoption business opportunities",
        f"{scope} technology trends outside cybersecurity",
    ]
