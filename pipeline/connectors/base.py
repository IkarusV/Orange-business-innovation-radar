import hashlib
import re
from datetime import timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from dateutil import parser as date_parser

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "ref", "source",
}

SOURCE_QUALITY = {
    "regulator": 5,
    "public_procurement": 5,
    "patent_office": 5,
    "analyst": 4,
    "tier1_press": 4,
    "trade_press": 3,
    "web_search": 3,
    "vendor": 2,
    "blog": 2,
    "unknown": 2,
}


def canonical_url(url):
    if not url:
        return None
    parsed = urlparse(url.strip())
    query = [
        (k, v) for k, v in parse_qsl(parsed.query)
        if k.lower() not in TRACKING_PARAMS
    ]
    return urlunparse((
        parsed.scheme.lower(), parsed.netloc.lower(),
        parsed.path.rstrip("/"), "", urlencode(query), "",
    ))


def title_hash(title):
    normalized = re.sub(r"\W+", " ", title.lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_date(value):
    if not value or not str(value).strip():
        return None
    try:
        parsed = date_parser.parse(str(value))
    except (ValueError, TypeError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def make_signal(connector, source_name, source_type, title, **kwargs):
    url = kwargs.get("url")
    url_c = canonical_url(url)
    return {
        "connector": connector,
        "source_name": source_name,
        "source_type": source_type,
        "source_quality": SOURCE_QUALITY.get(source_type, 2),
        "title": title,
        "url": url,
        "url_canonical": url_c,
        "guid": kwargs.get("guid") or url_c or title_hash(title),
        "published_at": normalize_date(kwargs.get("published_at")),
        "content": kwargs.get("content"),
        "geography": kwargs.get("geography"),
        "vertical_hint": kwargs.get("vertical_hint"),
        "domain_hint": kwargs.get("domain_hint"),
        "signal_type_hint": kwargs.get("signal_type_hint"),
        "extra": kwargs.get("extra", {}),
    }
