"""Local sentence-embedding of articles, routed by source_type and cached on disk.

One unified multilingual embedding space covering TED + CORDIS + OCDS (the
active institutional sources) - a single model since paraphrase-multilingual-
mpnet-base-v2 already covers all their languages natively, so there is no
English/multilingual split to maintain. RSS and gnews are out of scope (RSS is
backfill-only now, gnews is paused) and are not embedded here.
"""
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = REPO_ROOT / "data" / "embeddings"

MULTILINGUAL_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"

# Group name kept as "multilingual" (unchanged from the TED-only run) so the
# existing cache file is reused and only the new CORDIS/OCDS articles need
# encoding, not TED's already-embedded 5,350.
SOURCE_GROUPS = {
    "multilingual": {"source_types": ("ted", "cordis", "ocds_uk", "ocds_ua"), "model": MULTILINGUAL_MODEL},
}

SUMMARY_MAX_CHARS = 1000  # same truncation the LLM prompt uses in collector/client.py
BATCH_SIZE = 64

_loaded_models = {}


def group_for_source_type(source_type: str) -> str:
    for group, spec in SOURCE_GROUPS.items():
        if source_type in spec["source_types"]:
            return group
    raise ValueError(f"no embedding group configured for source_type {source_type!r}")


def model_name_for_group(group: str) -> str:
    return SOURCE_GROUPS[group]["model"]


def _model_slug(model_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model_name)


def _cache_path(group: str) -> Path:
    # the model id is part of the filename so a model swap can never silently reuse
    # vectors from a different embedding space under the same group name
    return CACHE_DIR / f"{group}__{_model_slug(model_name_for_group(group))}.npz"


def load_model(model_name: str):
    if model_name not in _loaded_models:
        from sentence_transformers import SentenceTransformer

        _loaded_models[model_name] = SentenceTransformer(model_name)
    return _loaded_models[model_name]


def build_text(title: str, summary: str) -> str:
    parts = [(title or "").strip()]
    trimmed = (summary or "").strip()[:SUMMARY_MAX_CHARS]
    if trimmed:
        parts.append(trimmed)
    return ". ".join(p for p in parts if p) or " "


def load_cache(group: str) -> dict:
    path = _cache_path(group)
    if not path.exists():
        return {}
    with np.load(path) as data:
        return {int(a): v for a, v in zip(data["article_ids"], data["vectors"])}


def save_cache(group: str, cache: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    article_ids = np.array(sorted(cache), dtype=np.int64)
    vectors = np.stack([cache[int(a)] for a in article_ids]).astype(np.float32)
    np.savez(_cache_path(group), article_ids=article_ids, vectors=vectors)


def articles_for_group(conn: sqlite3.Connection, group: str) -> list:
    placeholders = ",".join("?" for _ in SOURCE_GROUPS[group]["source_types"])
    return conn.execute(
        f"SELECT id, title, summary FROM articles WHERE source_type IN ({placeholders}) ORDER BY id",
        SOURCE_GROUPS[group]["source_types"],
    ).fetchall()


def encode_group(conn: sqlite3.Connection, group: str, log=None) -> dict:
    cache = load_cache(group)
    rows = articles_for_group(conn, group)
    missing = [r for r in rows if r[0] not in cache]

    if not missing:
        if log:
            log.info("[%s] %d articles already embedded, nothing to do", group, len(rows))
        return cache

    model_name = model_name_for_group(group)
    if log:
        log.info("[%s] encoding %d/%d articles with %s", group, len(missing), len(rows), model_name)
    model = load_model(model_name)

    texts = [build_text(title, summary) for _, title, summary in missing]
    started = datetime.now(timezone.utc)
    vectors = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=bool(log),
        convert_to_numpy=True,
    )
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()

    for (article_id, _, _), vector in zip(missing, vectors):
        cache[int(article_id)] = vector.astype(np.float32)
    save_cache(group, cache)

    if log:
        rate = len(missing) / elapsed if elapsed else 0
        log.info(
            "[%s] encoded %d articles in %.1fs (%.1f/s), dim=%d",
            group, len(missing), elapsed, rate, vectors.shape[1],
        )
    return cache


def matrix_for(cache: dict, article_ids) -> np.ndarray:
    return np.stack([cache[int(a)] for a in article_ids]).astype(np.float32)
