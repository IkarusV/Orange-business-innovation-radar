import calendar
import csv
import os
import re
from datetime import datetime, timezone

import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MD_FILE = os.path.join(SCRIPT_DIR, "flux_rss_innovation_radar.md")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "rss_digest.csv")

URL_PATTERN = re.compile(r"https?://[^\s)]+")
FIELDS = ["source", "title", "link", "guid", "published", "content"]
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
            feeds.append((name, url))
    return feeds


def strip_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(str(text), "html.parser")
    clean = soup.get_text(separator=" ")
    return re.sub(r"\s+", " ", clean).strip()


def normalize_date(value):
    if not value or not str(value).strip():
        return ""
    try:
        parsed = date_parser.parse(str(value))
    except (ValueError, TypeError, OverflowError):
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def raw_date(entry):
    parsed = entry.get("published_parsed")
    if parsed is None:
        return entry.get("published", "")
    timestamp = calendar.timegm(parsed)
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def raw_content(entry):
    if entry.get("content"):
        return entry.content[0].value
    return entry.get("summary", "")


def fetch_feed(name, url):
    feed = feedparser.parse(url, agent=USER_AGENT)
    articles = []
    for entry in feed.entries:
        title = strip_html(entry.get("title", ""))
        if not title:
            continue

        guid = entry.get("id", "") or entry.get("link", "")

        articles.append({
            "source": name,
            "title": title,
            "link": entry.get("link", ""),
            "guid": guid,
            "published": normalize_date(raw_date(entry)),
            "content": strip_html(raw_content(entry)),
        })
    return articles, feed.get("status")


def load_existing_guids(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["guid"] for row in reader}


def save_articles(articles, path):
    existing_guids = load_existing_guids(path)
    new_articles = [a for a in articles if a["guid"] not in existing_guids]

    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_articles)

    return len(new_articles)


if __name__ == "__main__":
    feeds = extract_feeds(MD_FILE)
    print(f"Found {len(feeds)} feed links in {MD_FILE}")

    all_articles = []
    for name, url in feeds:
        articles, status = fetch_feed(name, url)
        all_articles.extend(articles)
        print(f"{name}: {len(articles)} articles (status {status})")

    all_articles.sort(key=lambda a: a["source"])
    added = save_articles(all_articles, OUTPUT_FILE)
    print(f"Added {added} new entries to {OUTPUT_FILE}")