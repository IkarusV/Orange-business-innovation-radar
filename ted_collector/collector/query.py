from typing import Optional


def build_base_query(mapping_entry: dict) -> str:
    """OR every CPV/main-activity/keyword signal for one vertical (no sort, no date filter)."""
    parts = []
    for cpv in mapping_entry.get("cpv", []):
        parts.append(f"classification-cpv={cpv}")
    for main_activity in mapping_entry.get("main_activity", []):
        parts.append(f"main-activity={main_activity}")
    for keyword in mapping_entry.get("keywords", []):
        parts.append(f'FT~"{keyword}"')

    if not parts:
        raise ValueError("mapping entry has no CPV, main-activity, or keyword signals")

    return f"({' OR '.join(parts)})"


def build_query(base_query: str, before_date: Optional[str] = None) -> str:
    """Add an optional publication-date<=YYYYMMDD cutoff and the sort clause.

    No lower bound: sorted DESC, this naturally returns whatever's closest to
    (just before) the cutoff, rather than being capped to a fixed window that
    could come back thin for a low-volume vertical.
    """
    parts = [base_query]
    if before_date:
        parts.append(f"publication-date<={before_date}")
    return " AND ".join(parts) + " SORT BY publication-date DESC"
