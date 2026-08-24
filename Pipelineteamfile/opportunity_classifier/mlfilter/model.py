"""Logistic-regression usefulness classifier over sentence embeddings, plus
threshold selection for a single filtering policy: delete as much no_match
noise as possible while losing at most MAX_POSITIVE_LOSS of real signal.

One model is fitted per embedding space: vectors from different embedding
models share no geometry, so they cannot share a classifier.
"""
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, train_test_split

POSITIVE_STATUSES = ("classified", "needs_review")

TEST_FRACTION = 0.2
CV_FOLDS = 5
RANDOM_STATE = 20260822

C_GRID = (0.1, 1.0, 10.0)
VERTICAL_FEATURE_OPTIONS = (False, True)

MAX_POSITIVE_LOSS = 0.02
# the threshold is a quantile of the positive-class score distribution; estimating it
# from a single small split overfits badly (a 165-positive tune split once put TED's
# policy at 1.8% measured loss but 6.1% real loss on untouched data), so it is
# estimated from pooled out-of-fold predictions over the whole dev set
SAFETY_MARGIN = 0.5  # aim at half the allowed loss to absorb residual quantile noise


def label_for_status(status: str) -> int:
    return int(status in POSITIVE_STATUSES)


def build_features(vectors: np.ndarray, verticals, vertical_order, use_vertical: bool) -> np.ndarray:
    if not use_vertical:
        return vectors
    index = {v: i for i, v in enumerate(vertical_order)}
    one_hot = np.zeros((len(verticals), len(vertical_order)), dtype=np.float32)
    for row, vertical in enumerate(verticals):
        position = index.get(vertical)
        if position is not None:
            one_hot[row, position] = 1.0
    return np.hstack([vectors, one_hot])


def dev_test_split(n: int, y: np.ndarray):
    indices = np.arange(n)
    return train_test_split(
        indices, test_size=TEST_FRACTION, stratify=y, random_state=RANDOM_STATE,
    )


def out_of_fold_probs(features: np.ndarray, y: np.ndarray, C: float) -> np.ndarray:
    probs = np.zeros(len(y), dtype=np.float64)
    folds = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    for fit_idx, held_idx in folds.split(features, y):
        clf = fit(features[fit_idx], y[fit_idx], C)
        probs[held_idx] = clf.predict_proba(features[held_idx])[:, 1]
    return probs


def fit(features: np.ndarray, y: np.ndarray, C: float) -> LogisticRegression:
    clf = LogisticRegression(C=C, max_iter=3000, class_weight="balanced")
    clf.fit(features, y)
    return clf


def threshold_for_max_positive_loss(probs: np.ndarray, y: np.ndarray, max_loss: float) -> float:
    positive_probs = np.sort(probs[y == 1])
    if positive_probs.size == 0:
        return 0.0
    allowed = int(np.floor(max_loss * positive_probs.size))
    if allowed == 0:
        return float(positive_probs[0])
    # highest cut that still keeps (n_pos - allowed) positives: the prob of the
    # first positive we are permitted to keep
    return float(positive_probs[allowed])


def evaluate(probs: np.ndarray, y: np.ndarray, threshold: float) -> dict:
    kept = probs >= threshold
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    kept_pos = int((kept & (y == 1)).sum())
    kept_neg = int((kept & (y == 0)).sum())
    return {
        "threshold": float(threshold),
        "n_positive": n_pos,
        "n_negative": n_neg,
        "positive_recall": kept_pos / n_pos if n_pos else float("nan"),
        "positive_lost": n_pos - kept_pos,
        "positive_loss_rate": (n_pos - kept_pos) / n_pos if n_pos else float("nan"),
        "negative_deleted": n_neg - kept_neg,
        "negative_deletion_rate": (n_neg - kept_neg) / n_neg if n_neg else float("nan"),
        "precision_of_kept": kept_pos / int(kept.sum()) if kept.sum() else float("nan"),
        "corpus_kept_rate": int(kept.sum()) / len(y) if len(y) else float("nan"),
    }


def select_threshold(probs: np.ndarray, y: np.ndarray) -> float:
    return threshold_for_max_positive_loss(probs, y, MAX_POSITIVE_LOSS * SAFETY_MARGIN)


def train_group(vectors: np.ndarray, verticals, y: np.ndarray, vertical_order, log=None) -> dict:
    dev_idx, test_idx = dev_test_split(len(y), y)
    y_dev = y[dev_idx]

    best = None
    for use_vertical in VERTICAL_FEATURE_OPTIONS:
        features_dev = build_features(vectors, verticals, vertical_order, use_vertical)[dev_idx]
        for C in C_GRID:
            oof_probs = out_of_fold_probs(features_dev, y_dev, C)
            threshold = select_threshold(oof_probs, y_dev)
            scored = evaluate(oof_probs, y_dev, threshold)
            if log:
                log.info(
                    "  candidate C=%-5s vertical_feature=%-5s -> cv deletion %.1f%% "
                    "(positive recall %.1f%%)",
                    C, use_vertical,
                    100 * scored["negative_deletion_rate"], 100 * scored["positive_recall"],
                )
            if best is None or scored["negative_deletion_rate"] > best["cv"]["negative_deletion_rate"]:
                best = {
                    "C": C,
                    "use_vertical": use_vertical,
                    "threshold": threshold,
                    "oof_probs": oof_probs,
                    "cv": scored,
                }

    features = build_features(vectors, verticals, vertical_order, best["use_vertical"])
    clf = fit(features[dev_idx], y_dev, best["C"])
    test_probs = clf.predict_proba(features[test_idx])[:, 1]

    return {
        "C": best["C"],
        "use_vertical": best["use_vertical"],
        "clf": clf,
        "vertical_order": vertical_order,
        "threshold": best["threshold"],
        "split_sizes": {"dev": len(dev_idx), "test": len(test_idx), "cv_folds": CV_FOLDS},
        "cv": best["cv"],
        "test": evaluate(test_probs, y[test_idx], best["threshold"]),
    }


def score(trained: dict, vectors: np.ndarray, verticals) -> np.ndarray:
    features = build_features(vectors, verticals, trained["vertical_order"], trained["use_vertical"])
    return trained["clf"].predict_proba(features)[:, 1]
