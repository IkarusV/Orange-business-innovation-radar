import calendar
import re
from datetime import datetime, timezone

import feedparser
from bs4 import BeautifulSoup

from connectors.base import make_signal

URL_PATTERN = re.compile(r"https?://[^\s)]+")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def extract_feeds(md_path):
    feeds = []
    with open(md_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("- "):
                continue
            match = URL_PATTERN.search(line)
            if not match:
                continue
            url = match.group(0).rstrip(".,;:)")
            name = line[2:].split(" — ")[0].strip()
            source_type = "regulator" if "[regulator]" in line.lower() else "trade_press"
            feeds.append((name, url, source_type))
    return feeds


def strip_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(str(text), "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()


def entry_date(entry):
    parsed = entry.get("published_parsed")
    if parsed is None:
        return entry.get("published", "")
    timestamp = calendar.timegm(parsed)
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def entry_content(entry):
    if entry.get("content"):
        return entry.content[0].value
    return entry.get("summary", "")


def collect(md_path):
    signals = []
    for name, url, source_type in extract_feeds(md_path):
        feed = feedparser.parse(url, agent=USER_AGENT)
        signal_type = "regulation" if source_type == "regulator" else None
        for entry in feed.entries:
            title = strip_html(entry.get("title", ""))
            if not title:
                continue
            signals.append(make_signal(
                connector="rss",
                source_name=name,
                source_type=source_type,
                title=title,
                url=entry.get("link", ""),
                guid=entry.get("id", "") or entry.get("link", ""),
                published_at=entry_date(entry),
                content=strip_html(entry_content(entry)),
                signal_type_hint=signal_type,
            ))
        print(f"[rss] {name}: {len(feed.entries)} entries (status {feed.get('status')})")
    return signals
