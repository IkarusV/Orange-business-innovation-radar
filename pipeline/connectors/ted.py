from datetime import datetime, timedelta, timezone

import requests

from connectors.base import make_signal

TED_ENDPOINT = "https://api.ted.europa.eu/v3/notices/search"
NOTICE_URL = "https://ted.europa.eu/en/notice/-/detail/{}"

# CPV prefixes mapped to radar domains. Extend as needed.
CPV_DOMAIN_MAP = {
    "72": "cloud",             # IT services
    "302": "smart_industries", # computer equipment
    "32": "connectivity",      # radio, telecom networks
    "79417": "cybersecurity",  # safety consultancy
}


def build_query(lookback_days):
    since = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).strftime("%Y%m%d")
    cpv_clause = " OR ".join(
        f"classification-cpv={prefix}*" for prefix in CPV_DOMAIN_MAP
    )
    return f"(publication-date>={since}) AND ({cpv_clause})"


def domain_for_cpv(cpv_codes):
    for code in cpv_codes:
        for prefix, domain in CPV_DOMAIN_MAP.items():
            if str(code).startswith(prefix):
                return domain
    return None


def collect(lookback_days=30, limit=100):
    payload = {
        "query": build_query(lookback_days),
        "fields": [
            "publication-number", "notice-title", "publication-date",
            "classification-cpv", "place-of-performance", "buyer-name",
        ],
        "limit": limit,
        "page": 1,
    }
    try:
        response = requests.post(TED_ENDPOINT, json=payload, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[ted] request failed: {exc}")
        return []

    signals = []
    for notice in response.json().get("notices", []):
        pub_number = notice.get("publication-number", "")
        title_field = notice.get("notice-title", {})
        title = (
            title_field.get("eng")
            or next(iter(title_field.values()), "")
            if isinstance(title_field, dict) else str(title_field)
        )
        if isinstance(title, list):
            title = title[0] if title else ""
        if not title:
            continue
        cpv = notice.get("classification-cpv", []) or []
        place = notice.get("place-of-performance", []) or []
        signals.append(make_signal(
            connector="ted",
            source_name="TED",
            source_type="public_procurement",
            title=title,
            url=NOTICE_URL.format(pub_number),
            guid=f"ted:{pub_number}",
            published_at=notice.get("publication-date"),
            geography=", ".join(map(str, place)) if place else "EU",
            domain_hint=domain_for_cpv(cpv),
            vertical_hint="public_gov",
            signal_type_hint="buying_signal",
            extra={"cpv": cpv, "buyer": notice.get("buyer-name")},
        ))
    print(f"[ted] {len(signals)} notices")
    return signals
