from __future__ import annotations

import calendar
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from radar.db import connect, utcnow

USER_AGENT = "Orange-Innovation-Radar/0.1 (+student research prototype)"


def clean_text(value: str | None) -> str:
    text = BeautifulSoup(str(value or ""), "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def normalized_date(entry) -> str:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc).isoformat()
    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            result = date_parser.parse(raw)
            if result.tzinfo is None:
                result = result.replace(tzinfo=timezone.utc)
            return result.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError):
            pass
    return ""


def fetch_source(source: dict, limit: int = 30) -> tuple[list[dict], str]:
    feed = feedparser.parse(source["url"], agent=USER_AGENT)
    status = str(feed.get("status") or ("parse-error" if feed.get("bozo") else "ok"))
    articles = []
    for entry in feed.entries[:limit]:
        title = clean_text(entry.get("title"))
        link = canonical_url(entry.get("link", ""))
        if not title or not link:
            continue
        content_parts = entry.get("content") or []
        raw_content = content_parts[0].get("value", "") if content_parts else entry.get("summary", "")
        guid = str(entry.get("id") or link or hashlib.sha256(title.encode()).hexdigest())
        articles.append({"guid": guid, "title": title, "url": link, "published_at": normalized_date(entry), "content": clean_text(raw_content)[:12000]})
    return articles, status


def ingest_enabled_sources(limit_per_source: int = 30) -> dict:
    fetched = added = failures = 0
    with connect() as connection:
        sources = [dict(row) for row in connection.execute("SELECT * FROM sources WHERE enabled=1")]
    for source in sources:
        try:
            articles, status = fetch_source(source, limit_per_source)
            fetched += len(articles)
            with connect() as connection:
                before = connection.total_changes
                for article in articles:
                    connection.execute(
                        "INSERT OR IGNORE INTO articles(source_id,guid,title,url,published_at,content,fetched_at) VALUES(?,?,?,?,?,?,?)",
                        (source["id"], article["guid"], article["title"], article["url"], article["published_at"], article["content"], utcnow()),
                    )
                added += connection.total_changes - before
                connection.execute("UPDATE sources SET last_status=?,last_checked_at=? WHERE id=?", (status, utcnow(), source["id"]))
        except Exception as error:
            failures += 1
            with connect() as connection:
                connection.execute("UPDATE sources SET last_status=?,last_checked_at=? WHERE id=?", (f"error: {str(error)[:160]}", utcnow(), source["id"]))
    return {"fetched": fetched, "added": added, "failures": failures}
