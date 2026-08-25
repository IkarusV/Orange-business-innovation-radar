import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

import requests

from common.models import Article
from .query import TIER_CONFIDENCE, build_query, build_tier_queries

CORDIS_SEARCH_URL = "https://cordis.europa.eu/api/search/results"
PROJECT_URL_TEMPLATE = "https://cordis.europa.eu/project/id/{}"
PROJECT_JSON_URL_TEMPLATE = "https://cordis.europa.eu/project/id/{}?format=json"
REQUEST_TIMEOUT = 60
MAX_RETRIES = 4
REQUEST_SPACING_SECONDS = 1.0

# Verified live against the search API: `status` is a filterable field whose
# three values partition the project corpus exactly (SIGNED 24015 + CLOSED
# 31979 + TERMINATED 2978 = 58972 total). There is no "ONGOING" value - SIGNED
# covers both signed-not-yet-started and running projects. The search RESULTS
# payload does not carry the field, so status has to come from the per-project
# JSON view instead (see fetch_project_status).
PROJECT_STATUSES = ("SIGNED", "CLOSED", "TERMINATED")

# num>50 is silently ignored by the API and falls back to 10, so anything
# larger than one page has to be walked with p=1,2,3...
PAGE_SIZE = 50

# Total projects per vertical per run, split across three time buckets rather
# than just "most recent N" - sorted by start date, a single query only ever
# surfaces the last few months for a high-volume cluster code.
TOTAL_PER_VERTICAL = 250
ONE_YEAR_DAYS = 365
FIVE_YEAR_DAYS = 365 * 5

MONTH_PLACEHOLDER = re.compile(r"\{\{month_(\d{2})\}\}")


def _bucket_sizes(total: int) -> Tuple[int, int, int]:
    recent = total // 2
    remaining = total - recent
    one_year = remaining // 2
    five_year = remaining - one_year
    return recent, one_year, five_year


def _cutoff_date(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _parse_cordis_date(raw: Optional[str]) -> Optional[datetime]:
    """CORDIS search results render dates as '1 {{month_08}} 2014' - the month is
    an unresolved i18n placeholder, not a name, so dateutil can't touch it."""
    if not raw:
        return None
    match = MONTH_PLACEHOLDER.search(raw)
    if not match:
        return None
    parts = MONTH_PLACEHOLDER.sub(match.group(1), raw).split()
    if len(parts) != 3:
        return None
    try:
        day, month, year = (int(p) for p in parts)
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def _programme_codes(record: dict) -> List[str]:
    return [p.get("id") for p in (record.get("programme") or []) if p.get("id")]


def _programme_titles(record: dict) -> List[str]:
    return [p.get("title") for p in (record.get("programme") or []) if p.get("title")]


def _framework(codes: List[str]) -> Optional[str]:
    for code in codes:
        if code.startswith("HORIZON"):
            return "HORIZON"
        if code.startswith("H2020"):
            return "H2020"
        if code.startswith("FP7"):
            return "FP7"
    return None


def _parse_project(
    vertical: str, tier: str, time_window: str, record: dict, collected_at: datetime
) -> Article:
    project_id = record.get("id") or record.get("rcn")
    codes = _programme_codes(record)

    return Article(
        vertical=vertical,
        source_name="CORDIS",
        source_type="cordis",
        title=record.get("title") or record.get("acronym") or str(project_id),
        url=PROJECT_URL_TEMPLATE.format(project_id) if project_id else None,
        guid=f"cordis-{project_id}" if project_id else None,
        published_date=_parse_cordis_date(record.get("startDate")),
        summary=record.get("teaser"),
        collected_at=collected_at,
        confidence=TIER_CONFIDENCE.get(tier, "mid"),
        extra={
            "legal_basis": codes,
            "programme_titles": _programme_titles(record),
            "framework": _framework(codes),
            "matched_tier": tier,
            "acronym": record.get("acronym"),
            "coordinated_in": record.get("coordinatedIn"),
            "start_date": record.get("startDate"),
            "end_date": record.get("endDate"),
            "rcn": record.get("rcn"),
            "reference": record.get("reference"),
        },
        time_window=time_window,
    )


def _request_page(query: str, page: int, page_size: int) -> dict:
    params = {
        "q": query,
        "p": page,
        "num": page_size,
        "format": "json",
        "srt": "startDate:decreasing",
    }
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(CORDIS_SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(2 ** attempt)
            continue
        if response.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
            wait = float(response.headers.get("Retry-After", 2 ** attempt))
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response.json()
    return {}  # unreachable: last loop iteration always returns or raises


def _participant_countries(associations: list) -> List[str]:
    """Country codes of every organization on the project, in first-seen order.

    Verified against the live per-project JSON: each `organization` association
    carries `address.country` as a two-letter code and repeats it under
    `relations.regions[].isoCode`. The address is read first and the region
    block is the fallback, since only the latter exists for an organization with
    no postal address on record. Codes are returned exactly as CORDIS emits them
    - it uses the EU variants (EL for Greece, UK for the United Kingdom), which
    common.geography normalises rather than this collector.
    """
    countries = []
    for association in associations:
        if association.get("contenttype") != "organization":
            continue
        code = (association.get("address") or {}).get("country")
        if not code:
            regions = (association.get("relations") or {}).get("regions") or []
            code = next((r.get("isoCode") for r in regions if r.get("isoCode")), None)
        if code and code not in countries:
            countries.append(code)
    return countries


def fetch_project_status(project_id: str) -> Optional[dict]:
    """Project status, published-result count and participant countries for one
    project, from the per-project JSON view. Not folded into fetch_vertical():
    that would add one request per project (250 per vertical), so it is called
    on demand for the far smaller set of projects that actually reach
    classification.

    Returns {"status": SIGNED|CLOSED|TERMINATED, "result_count": int,
    "end_date": ISO date, "participant_countries": [...]} or None if the project
    cannot be read. result_count is the number of `result` associations -
    CORDIS's published deliverables and results for the project - which is what
    separates a closed project that actually reported something from one that
    just ended. participant_countries is multi-valued: a consortium project
    genuinely spans several countries and all of them are geography for it.
    """
    if not project_id:
        return None
    url = PROJECT_JSON_URL_TEMPLATE.format(project_id)
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"Accept": "application/json"})
        except requests.RequestException:
            if attempt == MAX_RETRIES - 1:
                return None
            time.sleep(2 ** attempt)
            continue
        if response.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
            time.sleep(float(response.headers.get("Retry-After", 2 ** attempt)))
            continue
        if response.status_code != 200:
            return None
        try:
            record = response.json()
        except ValueError:
            return None
        associations = (record.get("relations") or {}).get("associations") or []
        return {
            "status": record.get("status"),
            "result_count": sum(1 for a in associations if a.get("contenttype") == "result"),
            "end_date": record.get("endDate"),
            "participant_countries": _participant_countries(associations),
        }
    return None


def _run_search(query: str, limit: int) -> list:
    records = []
    page = 1
    while len(records) < limit:
        page_size = min(PAGE_SIZE, limit - len(records))
        payload = _request_page(query, page, page_size).get("payload") or {}
        batch = payload.get("results") or []
        if not batch:
            break
        records += batch
        if len(batch) < page_size:
            break
        page += 1
        time.sleep(REQUEST_SPACING_SECONDS)
    return records[:limit]


def _fill_bucket(
    vertical: str,
    time_window: str,
    tier_queries: List[Tuple[str, str]],
    cutoff: Optional[str],
    limit: int,
    collected_at: datetime,
) -> List[Article]:
    articles = []
    seen = set()
    for tier, base_query in tier_queries:
        if len(articles) >= limit:
            break
        for record in _run_search(build_query(base_query, cutoff), limit - len(articles)):
            project_id = record.get("id") or record.get("rcn")
            if project_id in seen:
                continue
            seen.add(project_id)
            articles.append(_parse_project(vertical, tier, time_window, record, collected_at))
        time.sleep(REQUEST_SPACING_SECONDS)
    return articles


def fetch_vertical(vertical: str, mapping_entry: dict) -> List[Article]:
    """Query CORDIS for one vertical across three time buckets: newest projects,
    projects starting before a ~1-year-back cutoff, and projects before a
    ~5-year-back cutoff (roughly 50% / 25% / 25% of TOTAL_PER_VERTICAL).

    The first two draw on Horizon Europe legalBasis codes; the third falls back
    to H2020 codes, since Horizon Europe only starts in 2021 and cannot fill a
    5-years-back bucket. Raises on failure; caller decides how to handle it.
    """
    horizon_tiers = build_tier_queries(mapping_entry, "horizon")
    h2020_tiers = build_tier_queries(mapping_entry, "h2020")
    recent_n, one_year_n, five_year_n = _bucket_sizes(TOTAL_PER_VERTICAL)

    buckets = [
        ("recent", horizon_tiers, None, recent_n),
        ("1y_ago", horizon_tiers, _cutoff_date(ONE_YEAR_DAYS), one_year_n),
        ("5y_ago", h2020_tiers, _cutoff_date(FIVE_YEAR_DAYS), five_year_n),
    ]

    collected_at = datetime.now(timezone.utc)
    articles = []
    for time_window, tier_queries, cutoff, limit in buckets:
        articles += _fill_bucket(
            vertical, time_window, tier_queries, cutoff, limit, collected_at
        )
    return articles
