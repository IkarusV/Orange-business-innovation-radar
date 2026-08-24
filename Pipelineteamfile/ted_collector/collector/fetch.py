import time
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

import requests
from dateutil import parser as dateutil_parser

from common.models import Article
from .query import build_base_query, build_query

TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 4
REQUEST_SPACING_SECONDS = 1.0  # between the 3 sub-requests of one vertical

# Total notices per vertical per run, split across three time buckets rather
# than just "most recent N" (which, sorted by date, never surfaces anything
# older than a few days for high-volume CPV codes).
TOTAL_PER_VERTICAL = 250
ONE_YEAR_DAYS = 365
FIVE_YEAR_DAYS = 365 * 5


def _bucket_sizes(total: int) -> Tuple[int, int, int]:
    active = total // 2
    remaining = total - active
    one_year = remaining // 2
    five_year = remaining - one_year
    return active, one_year, five_year  # e.g. 250 -> 125, 62, 63


def _cutoff_date(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).strftime("%Y%m%d")

FIELDS = [
    "publication-number",
    "publication-date",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "classification-cpv",
    "main-activity",
    "notice-type",
    "deadline",
    "total-value",
]


def _first_value(value):
    """Unwrap TED's per-lot arrays / multilingual dicts to a single representative value."""
    if isinstance(value, dict):
        if "eng" in value:
            return value["eng"]
        return next(iter(value.values()), None) if value else None
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _extract_url(links: dict) -> Optional[str]:
    if not isinstance(links, dict):
        return None
    for kind in ("html", "pdf", "xml"):
        by_lang = links.get(kind)
        if isinstance(by_lang, dict) and by_lang:
            return by_lang.get("eng") or next(iter(by_lang.values()))
    return None


def _parse_ted_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return dateutil_parser.parse(raw)
    except (ValueError, OverflowError):
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def _parse_notice(vertical: str, confidence: str, notice: dict, collected_at: datetime) -> Article:
    title = _first_value(notice.get("notice-title")) or notice.get("publication-number", "")
    buyer_name = _first_value(notice.get("buyer-name"))
    buyer_country = _first_value(notice.get("buyer-country"))
    notice_type = notice.get("notice-type")
    total_value = notice.get("total-value")
    deadline = notice.get("deadline")

    summary_bits = []
    if buyer_name:
        summary_bits.append(f"Buyer: {buyer_name}")
    if buyer_country:
        summary_bits.append(f"Country: {buyer_country}")
    if notice_type:
        summary_bits.append(f"Notice type: {notice_type}")
    if total_value:
        summary_bits.append(f"Value: {total_value}")
    summary = " | ".join(summary_bits) or None

    return Article(
        vertical=vertical,
        source_name="TED",
        source_type="ted",
        title=title,
        url=_extract_url(notice.get("links", {})),
        guid=notice.get("publication-number"),
        published_date=_parse_ted_date(notice.get("publication-date")),
        summary=summary,
        collected_at=collected_at,
        confidence=confidence,
        extra={
            "cpv": notice.get("classification-cpv"),
            "main_activity": notice.get("main-activity"),
            "buyer_country": notice.get("buyer-country"),
            "notice_type": notice_type,
            "total_value": total_value,
            "deadline": deadline,
        },
    )


def _run_search(query: str, limit: int, scope: str) -> list:
    body = {
        "query": query,
        "fields": FIELDS,
        "limit": limit,
        "page": 1,
        "scope": scope,
    }
    for attempt in range(MAX_RETRIES):
        response = requests.post(TED_SEARCH_URL, json=body, timeout=REQUEST_TIMEOUT)
        if response.status_code == 429 and attempt < MAX_RETRIES - 1:
            wait = float(response.headers.get("Retry-After", 2 ** attempt))
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response.json().get("notices", [])
    return []  # unreachable: last loop iteration always returns or raises


def fetch_vertical(vertical: str, mapping_entry: dict) -> List[Article]:
    """Query TED for one vertical across three time buckets: currently-active
    notices, notices from ~1 year ago, and notices from ~5 years ago
    (roughly 50% / 25% / 25% of TOTAL_PER_VERTICAL). Raises on failure;
    caller decides how to handle it.
    """
    base_query = build_base_query(mapping_entry)
    active_n, one_year_n, five_year_n = _bucket_sizes(TOTAL_PER_VERTICAL)

    raw_notices = []
    raw_notices += _run_search(build_query(base_query), active_n, scope="ACTIVE")
    time.sleep(REQUEST_SPACING_SECONDS)
    raw_notices += _run_search(
        build_query(base_query, _cutoff_date(ONE_YEAR_DAYS)), one_year_n, scope="ALL"
    )
    time.sleep(REQUEST_SPACING_SECONDS)
    raw_notices += _run_search(
        build_query(base_query, _cutoff_date(FIVE_YEAR_DAYS)), five_year_n, scope="ALL"
    )

    collected_at = datetime.now(timezone.utc)
    return [
        _parse_notice(vertical, "good", notice, collected_at)
        for notice in raw_notices
    ]
