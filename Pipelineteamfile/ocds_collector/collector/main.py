import logging
from pathlib import Path

import yaml

from .fetch import fetch_vertical_uk, fetch_vertical_ua
from common.storage import get_connection, insert_articles

MODULE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = MODULE_DIR.parent
MAPPING_CONFIG = MODULE_DIR / "config" / "mapping.yaml"
DB_PATH = REPO_ROOT / "data" / "articles.db"
LOG_PATH = REPO_ROOT / "logs" / "ocds_collector.log"


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
    log = logging.getLogger("ocds_collector")

    mapping = load_mapping(MAPPING_CONFIG)
    verticals = mapping["verticals"]
    countries = mapping["countries"]
    conn = get_connection(DB_PATH)

    totals = {"uk": 0, "ua": 0, "au": 0}
    verticals_ok = 0
    verticals_failed = 0

    au_cfg = countries.get("au", {})
    if not au_cfg.get("enabled"):
        log.info("SKIP [au] - %s", au_cfg.get("reason", "disabled").strip())

    for vertical, entry in verticals.items():
        cpv_list = entry.get("cpv", [])

        if countries.get("uk", {}).get("enabled"):
            try:
                articles, stats = fetch_vertical_uk(vertical, cpv_list)
                new_count = insert_articles(conn, articles)
                totals["uk"] += new_count
                verticals_ok += 1
                for window, fts_n, fts_scanned, cf_n, cf_scanned in stats:
                    log.info(
                        "OK   [uk/%s/%s] fts=%d/%d scanned, cf=%d/%d scanned",
                        vertical, window, fts_n, fts_scanned, cf_n, cf_scanned,
                    )
                log.info("OK   [uk/%s] %d notices, %d new", vertical, len(articles), new_count)
            except Exception as exc:
                verticals_failed += 1
                log.error("FAIL [uk/%s] - %s", vertical, exc)

        if countries.get("ua", {}).get("enabled"):
            try:
                articles, stats = fetch_vertical_ua(vertical, cpv_list)
                new_count = insert_articles(conn, articles)
                totals["ua"] += new_count
                verticals_ok += 1
                for window, matched, scanned, detail_fetched in stats:
                    log.info(
                        "OK   [ua/%s/%s] matched=%d scanned=%d detail_fetched=%d",
                        vertical, window, matched, scanned, detail_fetched,
                    )
                log.info("OK   [ua/%s] %d notices, %d new", vertical, len(articles), new_count)
            except Exception as exc:
                verticals_failed += 1
                log.error("FAIL [ua/%s] - %s", vertical, exc)

    conn.close()
    log.info(
        "Run complete: %d verticals OK, %d verticals failed, %d new (uk), %d new (ua), %d new (au)",
        verticals_ok, verticals_failed, totals["uk"], totals["ua"], totals["au"],
    )


if __name__ == "__main__":
    run()
