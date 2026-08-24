import time
from datetime import datetime, timezone
from typing import List, Optional, Set, Tuple

import requests
from dateutil import parser as dateutil_parser

from common.models import Article
from .query import (
    ONE_YEAR_DAYS,
    FIVE_YEAR_DAYS,
    bucket_sizes,
    cutoff_iso_date,
    extract_uk_cpv_codes,
    extract_ua_cpv_codes,
    matches_any_division,
)

REQUEST_TIMEOUT = 30
MAX_RETRIES = 4
REQUEST_SPACING_SECONDS = 0.3  # courtesy delay between paged requests

# UK: FTS + Contracts Finder return full release payloads per page (CPV data
# included), so a page is "free" beyond the one request - a generous page-scan
# cap is affordable.
UK_TOTAL_PER_VERTICAL = 250
UK_PAGE_LIMIT = 100  # server-enforced max on both UK endpoints
UK_MAX_PAGES_PER_BUCKET_SOURCE = 5  # scan up to 500 releases/bucket/source before giving up

# Ukraine: ProZorro's list endpoint is id+dateModified only (opt_fields is a
# confirmed no-op) - CPV only appears on the full per-tender GET, so every
# candidate costs a second request. Budget kept deliberately smaller than UK/TED
# because of that N+1 cost, not because the data is thinner.
UA_TOTAL_PER_VERTICAL = 60
UA_PAGE_LIMIT = 100
UA_MAX_CANDIDATES_PER_BUCKET = 60  # detail-fetch at most this many tenders/bucket
UA_DETAIL_SPACING_SECONDS = 0.05

FTS_URL = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
CF_URL = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
PROZORRO_LIST_URL = "https://public.api.openprocurement.org/api/2.5/tenders"
PROZORRO_DETAIL_URL = "https://public.api.openprocurement.org/api/2.5/tenders/{id}"

BUCKET_PLAN = [("recent", None), ("1y_ago", ONE_YEAR_DAYS), ("5y_ago", FIVE_YEAR_DAYS)]


def _get_with_retry(url: str, params: Optional[dict] = None) -> dict:
    """GET with retry-with-backoff on 429/5xx - both UK endpoints and ProZorro
    are public institutional APIs with no key, and rate limiting there is
    normal (same reasoning as ted_collector's retry wrapper).
    """
    for attempt in range(MAX_RETRIES):
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code == 429 and attempt < MAX_RETRIES - 1:
            wait = float(response.headers.get("Retry-After", 2 ** attempt))
            time.sleep(wait)
            continue
        if response.status_code >= 500 and attempt < MAX_RETRIES - 1:
            time.sleep(2 ** attempt)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"exhausted retries for {url}")


def _parse_iso(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return dateutil_parser.parse(raw)
    except (ValueError, OverflowError):
        return None


# ---------------------------------------------------------------------------
# UK: Find a Tender + Contracts Finder
# ---------------------------------------------------------------------------


def _extract_uk_document_url(release: dict, domain_substring: str) -> Optional[str]:
    candidates = []
    tender = release.get("tender") or {}
    candidates += tender.get("documents", []) or []
    for award in release.get("awards", []) or []:
        candidates += award.get("documents", []) or []
    for contract in release.get("contracts", []) or []:
        candidates += contract.get("documents", []) or []
    for doc in candidates:
        url = doc.get("url")
        if url and domain_substring in url:
            return url
    return None


def _parse_uk_release(
    vertical: str, release: dict, source_label: str, sub_source: str, cpv_codes: Set[str]
) -> Article:
    tender = release.get("tender") or {}
    release_id = release.get("id")
    title = tender.get("title") or release_id or ""
    buyer = release.get("buyer") or {}
    buyer_name = buyer.get("name")

    value, currency = None, None
    tender_value = tender.get("value")
    if isinstance(tender_value, dict):
        value, currency = tender_value.get("amount"), tender_value.get("currency")
    if value is None:
        for award in release.get("awards", []) or []:
            av = award.get("value")
            if isinstance(av, dict):
                value, currency = av.get("amount"), av.get("currency")
                break

    if sub_source == "fts":
        # Verified live: Notice/{release id} resolves for both tender- and
        # award-stage FTS releases - constructing beats relying on documents[]
        # being present (tender-stage releases often have none).
        url = f"https://www.find-tender.service.gov.uk/Notice/{release_id}"
    else:
        url = _extract_uk_document_url(release, "contractsfinder.service.gov.uk")

    stage = release.get("tag")
    summary_bits = []
    if buyer_name:
        summary_bits.append(f"Buyer: {buyer_name}")
    if value is not None:
        summary_bits.append(f"Value: {value} {currency or ''}".strip())
    if stage:
        summary_bits.append(f"Stage: {','.join(stage)}")
    summary = " | ".join(summary_bits) or None

    return Article(
        vertical=vertical,
        source_name=source_label,
        source_type="ocds_uk",
        title=title,
        url=url,
        guid=f"UK-{sub_source.upper()}-{release_id}",
        published_date=_parse_iso(release.get("date")),
        summary=summary,
        collected_at=datetime.now(timezone.utc),
        confidence="good",
        extra={
            "cpv_codes": sorted(cpv_codes),
            "sub_source": sub_source,
            "buyer_name": buyer_name,
            "buyer_country": "GB",
            "stage": stage,
            "value": value,
            "currency": currency,
            "ocid": release.get("ocid"),
        },
    )


def _fetch_uk_source_bucket(
    base_url: str,
    date_param: Optional[Tuple[str, str]],
    cpv_list: List[str],
    target_n: int,
    vertical: str,
    source_label: str,
    sub_source: str,
) -> Tuple[List[Article], int]:
    if target_n <= 0:
        return [], 0
    collected: List[Article] = []
    params = {"limit": UK_PAGE_LIMIT}
    if date_param:
        params[date_param[0]] = date_param[1]
    next_url, next_params = base_url, params
    pages, scanned = 0, 0

    while len(collected) < target_n and pages < UK_MAX_PAGES_PER_BUCKET_SOURCE:
        data = _get_with_retry(next_url, next_params)
        releases = data.get("releases", [])
        scanned += len(releases)
        for release in releases:
            codes = extract_uk_cpv_codes(release)
            if matches_any_division(codes, cpv_list):
                collected.append(_parse_uk_release(vertical, release, source_label, sub_source, codes))
                if len(collected) >= target_n:
                    break
        pages += 1
        next_link = (data.get("links") or {}).get("next")
        if not next_link or not releases:
            break
        next_url, next_params = next_link, None  # next_link is a full URL already
        time.sleep(REQUEST_SPACING_SECONDS)

    return collected, scanned


def fetch_vertical_uk(vertical: str, cpv_list: List[str]) -> Tuple[List[Article], list]:
    """Query FTS + Contracts Finder for one vertical across 3 buckets (recent /
    ~1y ago / ~5y ago), splitting each bucket's target 50/50 between the two
    UK sub-sources. Returns (articles, stats) where stats is a list of
    (window, fts_matched, fts_scanned, cf_matched, cf_scanned) for logging.
    """
    recent_n, y1_n, y5_n = bucket_sizes(UK_TOTAL_PER_VERTICAL)
    plan = [("recent", None, recent_n), ("1y_ago", ONE_YEAR_DAYS, y1_n), ("5y_ago", FIVE_YEAR_DAYS, y5_n)]

    all_articles: List[Article] = []
    stats = []
    for window_name, days_ago, target_n in plan:
        cutoff = cutoff_iso_date(days_ago)
        half = target_n // 2
        other_half = target_n - half

        fts_param = ("updatedTo", f"{cutoff}T23:59:59") if cutoff else None
        cf_param = ("publishedTo", f"{cutoff}T23:59:59Z") if cutoff else None

        fts_articles, fts_scanned = _fetch_uk_source_bucket(
            FTS_URL, fts_param, cpv_list, half, vertical, "UK Find a Tender", "fts"
        )
        cf_articles, cf_scanned = _fetch_uk_source_bucket(
            CF_URL, cf_param, cpv_list, other_half, vertical, "UK Contracts Finder", "contracts_finder"
        )
        for article in fts_articles + cf_articles:
            article.time_window = window_name
        all_articles.extend(fts_articles)
        all_articles.extend(cf_articles)
        stats.append((window_name, len(fts_articles), fts_scanned, len(cf_articles), cf_scanned))

    return all_articles, stats


# ---------------------------------------------------------------------------
# Ukraine: ProZorro
# ---------------------------------------------------------------------------


def _parse_ua_tender(vertical: str, tender: dict, cpv_codes: Set[str]) -> Article:
    tender_id_human = tender.get("tenderID")
    title = tender.get("title") or tender_id_human or tender.get("id", "")
    procuring_entity = tender.get("procuringEntity") or {}
    buyer_name = procuring_entity.get("name")

    value, currency = None, None
    tender_value = tender.get("value")
    if isinstance(tender_value, dict):
        value, currency = tender_value.get("amount"), tender_value.get("currency")

    status = tender.get("status")
    summary_bits = []
    if buyer_name:
        summary_bits.append(f"Buyer: {buyer_name}")
    if value is not None:
        summary_bits.append(f"Value: {value} {currency or ''}".strip())
    if status:
        summary_bits.append(f"Status: {status}")
    summary = " | ".join(summary_bits) or None

    return Article(
        vertical=vertical,
        source_name="Ukraine ProZorro",
        source_type="ocds_ua",
        title=title,
        url=f"https://prozorro.gov.ua/tender/{tender_id_human}" if tender_id_human else None,
        guid=f"UA-PROZORRO-{tender.get('id')}",
        published_date=_parse_iso(tender.get("dateModified") or tender.get("dateCreated")),
        summary=summary,
        collected_at=datetime.now(timezone.utc),
        confidence="good",
        extra={
            "cpv_codes": sorted(cpv_codes),
            "buyer_name": buyer_name,
            "buyer_country": "UA",
            "status": status,
            "procurement_method_type": tender.get("procurementMethodType"),
            "value": value,
            "currency": currency,
            "tender_id": tender_id_human,
        },
    )


def _fetch_ua_bucket(
    cutoff: Optional[str], cpv_list: List[str], target_n: int, vertical: str
) -> Tuple[List[Article], int, int]:
    if target_n <= 0:
        return [], 0, 0
    collected: List[Article] = []
    params = {"limit": UA_PAGE_LIMIT, "descending": 1}
    if cutoff:
        # jump-to-cutoff via offset, verified live: an ISO-datetime offset
        # value + descending=1 returns entries with dateModified<=cutoff,
        # newest-first - the plain "field<=cutoff sorted DESC" pattern, no
        # fixed window.
        params["offset"] = f"{cutoff}T23:59:59+03:00"
    scanned, detail_fetched = 0, 0

    while len(collected) < target_n and scanned < UA_MAX_CANDIDATES_PER_BUCKET:
        data = _get_with_retry(PROZORRO_LIST_URL, params)
        entries = data.get("data", [])
        if not entries:
            break
        for entry in entries:
            if scanned >= UA_MAX_CANDIDATES_PER_BUCKET or len(collected) >= target_n:
                break
            scanned += 1
            tender_id = entry.get("id")
            if not tender_id:
                continue
            try:
                detail = _get_with_retry(PROZORRO_DETAIL_URL.format(id=tender_id))
            except requests.HTTPError:
                continue
            detail_fetched += 1
            tender = detail.get("data", {})
            codes = extract_ua_cpv_codes(tender)
            if matches_any_division(codes, cpv_list):
                collected.append(_parse_ua_tender(vertical, tender, codes))
            time.sleep(UA_DETAIL_SPACING_SECONDS)

        next_page = data.get("next_page") or {}
        next_offset = next_page.get("offset")
        if not next_offset or scanned >= UA_MAX_CANDIDATES_PER_BUCKET:
            break
        params = {"limit": UA_PAGE_LIMIT, "descending": 1, "offset": next_offset}
        time.sleep(REQUEST_SPACING_SECONDS)

    return collected, scanned, detail_fetched


def fetch_vertical_ua(vertical: str, cpv_list: List[str]) -> Tuple[List[Article], list]:
    """Query ProZorro for one vertical across 3 buckets. Returns
    (articles, stats) where stats is (window, matched, scanned, detail_fetched).
    """
    recent_n, y1_n, y5_n = bucket_sizes(UA_TOTAL_PER_VERTICAL)
    plan = [("recent", None, recent_n), ("1y_ago", ONE_YEAR_DAYS, y1_n), ("5y_ago", FIVE_YEAR_DAYS, y5_n)]

    all_articles: List[Article] = []
    stats = []
    for window_name, days_ago, target_n in plan:
        cutoff = cutoff_iso_date(days_ago)
        articles, scanned, detail_fetched = _fetch_ua_bucket(cutoff, cpv_list, target_n, vertical)
        for article in articles:
            article.time_window = window_name
        all_articles.extend(articles)
        stats.append((window_name, len(articles), scanned, detail_fetched))
        time.sleep(REQUEST_SPACING_SECONDS)

    return all_articles, stats
