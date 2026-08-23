"""Query-building and CPV-matching helpers shared by the UK and Ukraine fetchers.

Neither UK endpoint (Find a Tender, Contracts Finder) nor Ukraine's ProZorro
feed supports server-side CPV filtering (confirmed live - see README), so
matching happens client-side here: pull whatever CPV/ДК021 classification
codes are attached to a release/tender, and compare their **division** (first
2 digits) against the vertical's mapped CPV codes. Division-level, not exact,
for the same reason TED's own CPV matching is division-broad - and because
Ukraine's ДК021 codes carry a checksum suffix TED-style codes don't
(e.g. "14410000-8" vs "14000000").
"""
from datetime import date, timedelta
from typing import Iterable, List, Optional, Set

ONE_YEAR_DAYS = 365
FIVE_YEAR_DAYS = 365 * 5


def cpv_division(code: str) -> str:
    """First 2 digits of a CPV/ДК021 code, stripping any '-N' checksum suffix."""
    return code.split("-", 1)[0][:2]


def matches_any_division(found_codes: Iterable[str], target_cpvs: Iterable[str]) -> bool:
    target_divisions = {cpv_division(c) for c in target_cpvs}
    return any(cpv_division(c) in target_divisions for c in found_codes)


def extract_uk_cpv_codes(release: dict) -> Set[str]:
    """Walk a UK OCDS release (FTS or Contracts Finder) for every CPV code
    attached anywhere - tender.classification, tender.items[], awards[].items[].
    """
    codes: Set[str] = set()

    def _take(classification: Optional[dict]) -> None:
        if isinstance(classification, dict) and classification.get("scheme") == "CPV":
            code_id = classification.get("id")
            if code_id:
                codes.add(str(code_id))

    tender = release.get("tender") or {}
    _take(tender.get("classification"))
    for item in tender.get("items", []) or []:
        _take(item.get("classification"))
        for extra in item.get("additionalClassifications", []) or []:
            _take(extra)

    for award in release.get("awards", []) or []:
        for item in award.get("items", []) or []:
            _take(item.get("classification"))
            for extra in item.get("additionalClassifications", []) or []:
                _take(extra)

    return codes


# Confirmed live 2026-08-22: ProZorro's classification scheme label is NOT
# stable "CPV" the way TED's is. A 2015-era tender used scheme "CPV" with a
# CPV-format id (e.g. "14410000-8"); current tenders instead use scheme
# "ДК021" (Ukraine's own name for its national CPV adaptation) with the same
# CPV-format id (e.g. "03220000-9", a real CPV code for produce). Same code
# space, different label depending on when the tender was created - both are
# accepted here. items[].additionalClassifications uses a genuinely different
# scheme (ДКПП, product-by-economic-activity) and is deliberately not scanned.
UA_CPV_SCHEMES = {"CPV", "ДК021"}


def extract_ua_cpv_codes(tender: dict) -> Set[str]:
    """Walk a ProZorro tender detail for CPV/ДК021 codes on items[].classification
    (and the rare top-level tender.classification, seen on some record shapes).
    """
    codes: Set[str] = set()

    def _take(classification) -> None:
        if isinstance(classification, dict) and classification.get("scheme") in UA_CPV_SCHEMES:
            code_id = classification.get("id")
            if code_id:
                codes.add(str(code_id))

    _take(tender.get("classification"))
    for item in tender.get("items", []) or []:
        _take(item.get("classification"))
    return codes


def cutoff_iso_date(days_ago: Optional[int]) -> Optional[str]:
    """YYYY-MM-DD cutoff, or None for 'no cutoff' (current/recent bucket)."""
    if days_ago is None:
        return None
    return (date.today() - timedelta(days=days_ago)).isoformat()


def bucket_sizes(total: int) -> "tuple[int, int, int]":
    """Same 50/25/25 split TED uses: recent / ~1y ago / ~5y ago."""
    recent = total // 2
    remaining = total - recent
    one_year = remaining // 2
    five_year = remaining - one_year
    return recent, one_year, five_year


BUCKETS: List[tuple] = [
    ("recent", None),
    ("1y_ago", ONE_YEAR_DAYS),
    ("5y_ago", FIVE_YEAR_DAYS),
]
