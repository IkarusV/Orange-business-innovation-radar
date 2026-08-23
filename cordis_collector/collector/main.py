import logging
from pathlib import Path

import yaml

from .fetch import fetch_vertical
from common.storage import get_connection, insert_articles

MODULE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = MODULE_DIR.parent
MAPPING_CONFIG = MODULE_DIR / "config" / "mapping.yaml"
DB_PATH = REPO_ROOT / "data" / "articles.db"
LOG_PATH = REPO_ROOT / "logs" / "cordis_collector.log"


def setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
    )


def load_mapping(config_path: Path) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run() -> None:
    setup_logging()
    log = logging.getLogger("cordis_collector")

    mapping = load_mapping(MAPPING_CONFIG)
    conn = get_connection(DB_PATH)

    verticals_ok = 0
    verticals_failed = 0
    total_new = 0

    for vertical, entry in mapping.items():
        try:
            articles = fetch_vertical(vertical, entry)
            new_count = insert_articles(conn, articles)
            total_new += new_count
            verticals_ok += 1
            buckets = {}
            tiers = {}
            for article in articles:
                buckets[article.time_window] = buckets.get(article.time_window, 0) + 1
                tier = article.extra["matched_tier"]
                tiers[tier] = tiers.get(tier, 0) + 1
            log.info(
                "OK   [%s] quality=%s - %d projects, buckets=%s tiers=%s, %d new",
                vertical, entry.get("mapping_quality"), len(articles), buckets, tiers, new_count,
            )
        except Exception as exc:
            verticals_failed += 1
            log.error("FAIL [%s] - %s", vertical, exc)

    conn.close()
    log.info(
        "Run complete: %d verticals OK, %d verticals failed, %d new projects",
        verticals_ok, verticals_failed, total_new,
    )


if __name__ == "__main__":
    run()
