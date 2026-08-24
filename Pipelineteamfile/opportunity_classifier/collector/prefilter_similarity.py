"""Zero-token pre-filter: local TF-IDF cosine similarity of an article against the taxonomy."""
import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "config" / "taxonomy.json"

DEFAULT_THRESHOLD = 0.05


class TaxonomySimilarityScorer:
    def __init__(self, taxonomy_path: Path = TAXONOMY_PATH):
        with open(taxonomy_path, "r", encoding="utf-8") as f:
            taxonomy = json.load(f)

        entries = list(taxonomy["use_cases"]) + list(taxonomy["technologies"])
        self.entry_ids = [entry["id"] for entry in entries]
        documents = [f'{entry["label"]}: {entry["definition"]}' for entry in entries]

        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            sublinear_tf=True,
            ngram_range=(1, 2),
            min_df=1,
        )
        self.taxonomy_matrix = self.vectorizer.fit_transform(documents)

    def score(self, title: str, summary: str = None) -> float:
        text = f"{title or ''} {summary or ''}".strip()
        if not text:
            return 0.0
        vector = self.vectorizer.transform([text])
        if vector.nnz == 0:
            return 0.0
        # tf-idf rows are L2-normalized, so the dot product is already cosine similarity
        similarities = linear_kernel(vector, self.taxonomy_matrix)[0]
        return float(similarities.max())

    def best_match(self, title: str, summary: str = None) -> tuple:
        text = f"{title or ''} {summary or ''}".strip()
        if not text:
            return None, 0.0
        vector = self.vectorizer.transform([text])
        if vector.nnz == 0:
            return None, 0.0
        similarities = linear_kernel(vector, self.taxonomy_matrix)[0]
        index = int(similarities.argmax())
        return self.entry_ids[index], float(similarities[index])

    def passes_similarity(self, title: str, summary: str = None,
                          threshold: float = DEFAULT_THRESHOLD) -> bool:
        return self.score(title, summary) >= threshold


_scorer = None


def get_scorer() -> TaxonomySimilarityScorer:
    global _scorer
    if _scorer is None:
        _scorer = TaxonomySimilarityScorer()
    return _scorer


def score(title: str, summary: str = None) -> float:
    return get_scorer().score(title, summary)


def passes_similarity(title: str, summary: str = None,
                      threshold: float = DEFAULT_THRESHOLD) -> bool:
    return get_scorer().passes_similarity(title, summary, threshold)


if __name__ == "__main__":
    examples = [
        ("Factory sensors feed a machine learning model to predict bearing failures", None),
        ("Port operator deploys computer vision to inspect containers for damage",
         "Cameras and image recognition flag damaged containers automatically."),
        ("Utility rolls out digital twin of its water network",
         "Simulation model of the distribution grid supports leak detection."),
        ("Retailer builds cloud data platform for demand forecasting", None),
        ("Insurance services procurement notice for a municipal building", None),
        ("School catering services framework agreement", None),
        ("Group appoints new chief financial officer", "The board named a successor effective next quarter."),
        ("Road salt supply for winter maintenance", None),
        (None, None),
    ]

    scorer = TaxonomySimilarityScorer()
    for title, summary in examples:
        entry_id, value = scorer.best_match(title, summary)
        keep = scorer.passes_similarity(title, summary)
        print(f"{value:.4f}  keep={str(keep):5}  match={entry_id or '-':<38}  {title!r}")
