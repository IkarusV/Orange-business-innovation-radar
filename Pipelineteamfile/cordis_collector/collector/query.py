from typing import List, Optional, Tuple

CONTENT_TYPE_CLAUSE = "contenttype='project'"

# Confidence written to the DB for rows a tier produced. Not configured per
# vertical: it is a property of which signal actually matched, and a keyword
# match is a weaker claim than a legalBasis match regardless of vertical.
TIER_CONFIDENCE = {
    "legal_basis": "good",
    "call_code": "good",
    "keyword": "mid",
}


def _code_clauses(codes: List[str]) -> List[str]:
    return [f"programme/code='{code}'" for code in codes]


def _keyword_clauses(keywords: List[str]) -> List[str]:
    return [f"objective='{keyword}'" for keyword in keywords]


def build_tier_queries(mapping_entry: dict, framework: str) -> List[Tuple[str, str]]:
    """Ordered fallback cascade for one vertical within one framework programme.

    Tier 1 is the legalBasis/programme code (the application-area signal this
    module is built around), tier 2 the destination-level call codes that split
    verticals a cluster code alone conflates (CL4 -> Manufacturing vs Aerospace),
    tier 3 free-text. A bucket is filled from tier 1 first and only tops up from
    the next tier if it came back short, so the weaker signals never dilute the
    stronger one - OR-ing them into a single query would, since results come
    back sorted by date and not by which clause matched.

    `framework` is "horizon" (2021-2027) or "h2020" (2014-2020); their legalBasis
    namespaces are disjoint, so a bucket draws from one or the other, never both.
    """
    if framework == "horizon":
        tiers = [
            ("legal_basis", _code_clauses(mapping_entry.get("horizon_codes") or [])),
            ("call_code", _code_clauses(mapping_entry.get("horizon_calls") or [])),
        ]
    elif framework == "h2020":
        tiers = [
            ("legal_basis", _code_clauses(mapping_entry.get("h2020_codes") or [])),
        ]
    else:
        raise ValueError(f"unknown framework: {framework}")

    tiers.append(("keyword", _keyword_clauses(mapping_entry.get("keywords") or [])))

    queries = [(name, f"({' OR '.join(parts)})") for name, parts in tiers if parts]
    if not queries:
        raise ValueError(f"mapping entry has no {framework} code or keyword signals")
    return queries


def build_query(base_query: str, before_date: Optional[str] = None) -> str:
    """Add the project-record filter and an optional startDate<= cutoff.

    No lower bound: paired with srt=startDate:decreasing this returns whatever
    started closest to (just before) the cutoff, so a low-volume vertical still
    fills its bucket instead of coming back thin on a fixed window.
    """
    parts = [CONTENT_TYPE_CLAUSE, base_query]
    if before_date:
        parts.append(f"startDate<='{before_date}'")
    return " AND ".join(parts)
