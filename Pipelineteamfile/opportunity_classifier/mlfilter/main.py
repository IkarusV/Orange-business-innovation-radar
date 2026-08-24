"""End-to-end ML noise pre-filter: embed every article, train a usefulness
classifier on the LLM's own labels, pick a single aggressive threshold
(max 2% real-signal loss) on held-out data, and score the whole corpus into
ml_noise_scores.

Recommendation only — nothing is ever deleted from articles, and nothing
downstream consumes this table yet (not wired into select_corpus.py).
"""
import argparse
import logging
import time
from pathlib import Path

import numpy as np

from . import embeddings as embeddings_mod
from . import model as model_mod
from . import storage as mlfilter_storage
from common.storage import get_connection

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = REPO_ROOT / "data" / "articles.db"
LOG_PATH = REPO_ROOT / "logs" / "ml_noise_filter.log"


def setup_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
    )
    log = logging.getLogger("ml_noise_filter")
    log.setLevel(logging.INFO)
    return log


def report_split(log: logging.Logger, group: str, split_name: str, metrics: dict) -> None:
    log.info(
        "  [%s] %-6s thr=%.4f | kept %.1f%% of corpus | positives lost %d/%d (%.2f%%) | "
        "no_match deleted %d/%d (%.1f%%) | precision of kept %.1f%%",
        group, split_name, metrics["threshold"],
        100 * metrics["corpus_kept_rate"],
        metrics["positive_lost"], metrics["n_positive"], 100 * metrics["positive_loss_rate"],
        metrics["negative_deleted"], metrics["n_negative"], 100 * metrics["negative_deletion_rate"],
        100 * metrics["precision_of_kept"],
    )


def run(groups=None) -> None:
    log = setup_logging()
    conn = get_connection(DB_PATH)
    mlfilter_storage.ensure_schema(conn)

    vertical_order = sorted(r[0] for r in conn.execute("SELECT DISTINCT vertical FROM articles"))
    targets = groups or list(embeddings_mod.SOURCE_GROUPS)
    t_start = time.time()

    for group in targets:
        source_types = embeddings_mod.SOURCE_GROUPS[group]["source_types"]
        model_name = embeddings_mod.model_name_for_group(group)
        log.info("=== group %s (%s) via %s ===", group, "/".join(source_types), model_name)

        t_embed = time.time()
        cache = embeddings_mod.encode_group(conn, group, log=log)
        embed_seconds = time.time() - t_embed

        labeled = mlfilter_storage.labeled_rows(conn, source_types)
        labeled = [r for r in labeled if r[0] in cache]
        article_ids = [r[0] for r in labeled]
        verticals = [r[1] for r in labeled]
        y = np.array([model_mod.label_for_status(r[2]) for r in labeled])
        vectors = embeddings_mod.matrix_for(cache, article_ids)

        log.info(
            "labeled rows: %d (%d positive / %d no_match, %.1f%% positive), embedding dim %d",
            len(y), int(y.sum()), int((y == 0).sum()), 100 * y.mean(), vectors.shape[1],
        )

        trained = model_mod.train_group(vectors, verticals, y, vertical_order, log=log)
        log.info(
            "selected: C=%s vertical_feature=%s | dev %d (%d-fold cv) / untouched test %d",
            trained["C"], trained["use_vertical"],
            trained["split_sizes"]["dev"], trained["split_sizes"]["cv_folds"],
            trained["split_sizes"]["test"],
        )
        report_split(log, group, "cv", trained["cv"])
        report_split(log, group, "test", trained["test"])

        all_articles = [r for r in mlfilter_storage.all_rows(conn, source_types) if r[0] in cache]
        all_ids = [r[0] for r in all_articles]
        all_verticals = [r[1] for r in all_articles]
        labeled_set = set(article_ids)

        t_score = time.time()
        probs = model_mod.score(trained, embeddings_mod.matrix_for(cache, all_ids), all_verticals)
        score_seconds = time.time() - t_score

        written = mlfilter_storage.write_scores(
            conn, group, model_name,
            [(aid, p, aid in labeled_set) for aid, p in zip(all_ids, probs)],
            trained["threshold"],
        )
        kept = int((probs >= trained["threshold"]).sum())
        log.info(
            "scored %d articles in %.1fs (embedding stage %.1fs) -> keeps %d (%.1f%%)",
            written, score_seconds, embed_seconds, kept, 100 * kept / written,
        )

    log.info("--- corpus totals ---")
    for row in conn.execute(
        """
        SELECT source_group, COUNT(*), SUM(keep_recommended)
        FROM ml_noise_scores GROUP BY source_group ORDER BY source_group
        """
    ):
        group, total, keep = row
        log.info("  %-13s %5d articles | keeps %5d (%.1f%%)", group, total, keep, 100 * keep / total)
    total, keep = conn.execute(
        "SELECT COUNT(*), SUM(keep_recommended) FROM ml_noise_scores"
    ).fetchone()
    log.info("  %-13s %5d articles | keeps %5d (%.1f%%)", "ALL", total, keep, 100 * keep / total)
    log.info("total wall time %.1fs", time.time() - t_start)
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--group", action="append", choices=sorted(embeddings_mod.SOURCE_GROUPS),
        help="restrict to one embedding group (repeatable); default is all",
    )
    args = parser.parse_args()
    run(groups=args.group)
