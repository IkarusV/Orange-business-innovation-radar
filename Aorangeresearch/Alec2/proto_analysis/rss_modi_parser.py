import argparse
import calendar
import csv
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time, timezone

import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_REGISTRY_FILE = os.path.join(SCRIPT_DIR, "source_registry.csv")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "rss_digest_v2.csv")

FIELDS = [
    "source",
    "source_category",
    "source_quality_default",
    "independence_group",
    "domain",
    "collection_method",
    "vertical_scope",
    "signal_types",
    "language",
    "feed_url",
    "title",
    "link",
    "guid",
    "published",
    "collected_at",
    "content",
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MAX_WORKERS = 5


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Collect RSS articles, optionally limited to a publication period."
    )
    period = parser.add_mutually_exclusive_group()
    period.add_argument(
        "--months",
        type=int,
        help="Collect entries published within this many calendar months before now.",
    )
    period.add_argument(
        "--days",
        type=int,
        help="Collect entries published within this many days before now.",
    )
    period.add_argument(
        "--start-date",
        help="First publication date to include (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        help="Last publication date to include (YYYY-MM-DD); requires --start-date.",
    )
    args = parser.parse_args()

    if args.months is not None and args.months < 1:
        parser.error("--months must be a positive integer")
    if args.days is not None and args.days < 1:
        parser.error("--days must be a positive integer")
    if args.end_date and not args.start_date:
        parser.error("--end-date requires --start-date")

    return args


def parse_cli_date(value, option_name):
    try:
        parsed_date = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise ValueError(f"{option_name} must use YYYY-MM-DD format") from error
    return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)


def publication_period(args, now=None):
    if args.months is None and args.days is None and not args.start_date:
        return None, None

    now = now or datetime.now(timezone.utc)
    if args.months is not None:
        return now - relativedelta(months=args.months), now
    if args.days is not None:
        return now - relativedelta(days=args.days), now

    start = parse_cli_date(args.start_date, "--start-date")
    if args.end_date:
        # Use the start of the following day so the requested end date is inclusive.
        end = parse_cli_date(args.end_date, "--end-date") + relativedelta(days=1)
    else:
        end = now

    if start >= end:
        raise ValueError("--start-date must be earlier than --end-date")
    return start, end


def filter_by_publication_period(articles, start, end):
    if start is None:
        return articles, 0, 0

    included = []
    outside_period = 0
    missing_date = 0
    for article in articles:
        published = article["published"]
        if not published:
            missing_date += 1
            continue
        try:
            published_at = datetime.fromisoformat(published)
        except ValueError:
            missing_date += 1
            continue
        if start <= published_at < end:
            included.append(article)
        else:
            outside_period += 1

    return included, outside_period, missing_date


def load_sources(path):
    required_fields = {
        "source",
        "feed_url",
        "source_category",
        "source_quality_default",
        "independence_group",
        "domain",
        "collection_method",
        "vertical_scope",
        "signal_types",
        "language",
        "active",
    }

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not required_fields.issubset(reader.fieldnames):
            missing = required_fields.difference(reader.fieldnames or [])
            raise ValueError(f"Source registry is missing columns: {sorted(missing)}")

        sources = []
        for row in reader:
            if row["active"].strip().lower() != "true":
                continue

            collection_method = row["collection_method"].strip().lower()
            if collection_method != "rss":
                continue

            required_values = (
                "source",
                "feed_url",
                "vertical_scope",
                "signal_types",
                "language",
            )
            missing_values = [field for field in required_values if not row[field].strip()]
            if missing_values:
                raise ValueError(
                    f"Active RSS source is missing values for {missing_values}: "
                    f"{row['source']!r}"
                )
            try:
                quality = int(row["source_quality_default"])
            except ValueError as error:
                raise ValueError(
                    f"Invalid source_quality_default for {row['source']!r}"
                ) from error
            if quality < 1 or quality > 5:
                raise ValueError(
                    f"source_quality_default must be 1-5 for {row['source']!r}"
                )

            sources.append({
                "source": row["source"].strip(),
                "feed_url": row["feed_url"].strip(),
                "source_category": row["source_category"].strip(),
                "source_quality_default": quality,
                "independence_group": row["independence_group"].strip(),
                "domain": row["domain"].strip(),
                "collection_method": collection_method,
                "vertical_scope": row["vertical_scope"].strip(),
                "signal_types": row["signal_types"].strip(),
                "language": row["language"].strip().lower(),
            })
    return sources


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


def fetch_feed(source):
    feed = feedparser.parse(source["feed_url"], agent=USER_AGENT)
    articles = []
    for entry in feed.entries:
        title = strip_html(entry.get("title", ""))
        if not title:
            continue

        guid = entry.get("id", "") or entry.get("link", "")

        articles.append({
            "source": source["source"],
            "source_category": source["source_category"],
            "source_quality_default": source["source_quality_default"],
            "independence_group": source["independence_group"],
            "domain": source["domain"],
            "collection_method": source["collection_method"],
            "vertical_scope": source["vertical_scope"],
            "signal_types": source["signal_types"],
            "language": source["language"],
            "feed_url": source["feed_url"],
            "title": title,
            "link": entry.get("link", ""),
            "guid": guid,
            "published": normalize_date(raw_date(entry)),
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "content": strip_html(raw_content(entry)),
        })
    return articles, feed.get("status")


def fetch_source(source):
    try:
        articles, status = fetch_feed(source)
        return source, articles, status, None
    except Exception as error:
        return source, [], None, error


def load_existing_guids(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != FIELDS:
            raise ValueError(
                f"{path} has an incompatible header. Rename or migrate it before running."
            )
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
    args = parse_arguments()
    try:
        period_start, period_end = publication_period(args)
    except ValueError as error:
        raise SystemExit(f"Error: {error}") from error

    if period_start is not None:
        print(
            "Publication period: "
            f"{period_start.isoformat()} to {period_end.isoformat()}"
        )

    sources = load_sources(SOURCE_REGISTRY_FILE)
    print(f"Found {len(sources)} active sources in {SOURCE_REGISTRY_FILE}")

    all_articles = []
    worker_count = min(MAX_WORKERS, len(sources))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(fetch_source, source) for source in sources]
        for future in as_completed(futures):
            source, articles, status, error = future.result()
            if error:
                print(f"{source['source']}: failed ({error})")
                continue
            all_articles.extend(articles)
            print(f"{source['source']}: {len(articles)} articles (status {status})")

    all_articles, outside_period, missing_date = filter_by_publication_period(
        all_articles, period_start, period_end
    )
    if period_start is not None:
        print(
            f"Period filter kept {len(all_articles)} entries; "
            f"excluded {outside_period} outside the period and "
            f"{missing_date} without a valid publication date."
        )

    all_articles.sort(key=lambda a: a["source"])
    added = save_articles(all_articles, OUTPUT_FILE)
    print(f"Added {added} new entries to {OUTPUT_FILE}")
