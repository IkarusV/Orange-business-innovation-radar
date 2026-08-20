import re
from difflib import SequenceMatcher

from connectors.base import title_hash

SIMILARITY_THRESHOLD = 0.90


def normalize(title):
    return re.sub(r"\W+", " ", title.lower()).strip()


def filter_duplicates(signals, conn):
    seen_hashes = {
        row["h"] for row in conn.execute(
            "SELECT DISTINCT lower(title) AS h FROM raw_signals"
        )
    }
    existing_hashes = {
        title_hash(h) for h in seen_hashes if h
    }

    kept, batch_titles = [], []
    for s in signals:
        h = title_hash(s["title"])
        if h in existing_hashes:
            continue
        norm = normalize(s["title"])
        if any(
            SequenceMatcher(None, norm, prev).ratio() >= SIMILARITY_THRESHOLD
            for prev in batch_titles
        ):
            continue
        existing_hashes.add(h)
        batch_titles.append(norm)
        kept.append(s)
    return kept
