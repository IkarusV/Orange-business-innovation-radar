from pathlib import Path
import argparse
from datetime import datetime, date

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ANALYSIS_DIR / "outputs"

ENRICHMENT_DIR = OUTPUT_DIR / "enrichment"
BASE_PATH = ENRICHMENT_DIR / "all_candidates_base.csv"
ENRICHED_PATH = ENRICHMENT_DIR / "enriched_candidates.csv"
REVIEW_QUEUE_PATH = ENRICHMENT_DIR / "enrichment_review_queue.csv"
SUMMARY_PATH = ENRICHMENT_DIR / "enrichment_summary.csv"
REVIEW_TEMPLATE_PATH = ENRICHMENT_DIR / "reviewed_enrichment.csv"

REQUIRED_COLUMNS = {
    "article_id",
    "vertical",
    "title",
    "summary",
    "url",
    "source_name",
    "source_type",
    "published_date",
    "time_window",
    "classification_status",
    "use_case_id",
    "technology_id",
    "classification_confidence",
    "classification_evidence",
    "ml_usefulness_probability",
    "ml_keep_recommended",
}

ENRICHMENT_COLUMNS = [
    "source_quality_prior",
    "source_independence_group",
    "source_role",
    "date_quality_flag",
    "signal_type",
    "signal_confidence",
    "orange_relevance",
    "orange_relevance_confidence",
    "orange_fit_basis",
    "orange_relevance_rationale",
    "event_key",
    "event_key_method",
    "enrichment_method",
    "enrichment_status",
    "review_status",
]

SOURCE_PRIORS = {
    "ted": {"prior": 0.90, "role": "primary_institutional"},
    "ocds_uk": {"prior": 0.90, "role": "primary_institutional"},
    "ocds_ua": {"prior": 0.90, "role": "primary_institutional"},
    "cordis": {"prior": 0.80, "role": "primary_institutional"},
    "rss": {"prior": 0.55, "role": "secondary_media"},
    "gnews": {"prior": 0.45, "role": "secondary_media"},
}

DEFAULT_PRIOR = {"prior": 0.30, "role": "unknown"}

VALID_SIGNAL_TYPES = {
    "regulation",
    "buying_signal",
    "market_trend",
    "market_move",
    "technology_maturity",
    "proof_signal",
    "unknown",
}

VALID_ORANGE_RELEVANCE = {"RELEVANT", "IRRELEVANT", "REVIEW"}
VALID_ORANGE_FIT_BASIS = {"explicit", "inferred", "unsupported"}
VALID_SOURCE_ROLES = {
    "primary_institutional",
    "primary_company",
    "secondary_media",
    "vendor",
    "unknown",
}
VALID_DATE_FLAGS = {"valid_past", "future_event", "missing", "invalid"}
VALID_ENRICHMENT_STATUSES = {
    "ready_for_scoring",
    "needs_review",
    "excluded",
}
VALID_REVIEW_STATUSES = {"pending", "completed", "excluded"}

REVIEW_TEMPLATE_COLUMNS = [
    "article_id",
    "vertical",
    "title",
    "summary",
    "url",
    "source_name",
    "source_type",
    "published_date",
    "classification_status",
    "use_case_id",
    "technology_id",
    "classification_confidence",
    "classification_evidence",
    "ml_usefulness_probability",
    "source_quality_prior",
    "source_role",
    "date_quality_flag",
    "signal_type",
    "signal_confidence",
    "orange_relevance",
    "orange_relevance_confidence",
    "orange_fit_basis",
    "orange_relevance_rationale",
    "review_status",
]


def find_candidate_files() -> list[Path]:
    files = sorted(OUTPUT_DIR.glob("*/candidate_queue.csv"))

    if not files:
        raise FileNotFoundError(
            "No candidate_queue.csv files found under Analysis/outputs."
        )

    return files


def load_candidate_queues() -> pd.DataFrame:
    datasets = []

    for file_path in find_candidate_files():
        dataframe = pd.read_csv(
            file_path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )
        datasets.append(dataframe)

    return pd.concat(datasets, ignore_index=True)


def validate_candidates(dataframe: pd.DataFrame) -> None:
    missing_columns = REQUIRED_COLUMNS - set(dataframe.columns)

    if missing_columns:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    empty_article_ids = dataframe["article_id"].str.strip().eq("")

    if empty_article_ids.any():
        raise ValueError(
            f"Found {empty_article_ids.sum()} empty article_id values."
        )

    duplicate_article_ids = dataframe[
        dataframe["article_id"].duplicated(keep=False)
    ]

    if not duplicate_article_ids.empty:
        duplicate_ids = sorted(
            duplicate_article_ids["article_id"].unique()
        )
        raise ValueError(
            "Duplicate article_id values found: "
            + ", ".join(duplicate_ids[:10])
        )


def add_blank_enrichment_columns(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    result = dataframe.copy()

    for column in ENRICHMENT_COLUMNS:
        if column not in result.columns:
            result[column] = ""

    return result


def classify_date(date_str: str, today: date) -> str:
    if not date_str or not date_str.strip():
        return "missing"

    # The source database uses ISO-8601 values such as
    # ``2026-08-24T00:00:00+00:00``. ``datetime.fromisoformat`` supports
    # both those timezone-aware values and date-only values.
    normalized_date = date_str.strip().replace("Z", "+00:00")

    try:
        parsed = datetime.fromisoformat(normalized_date).date()
    except ValueError:
        return "invalid"

    if parsed > today:
        return "future_event"

    return "valid_past"


def build_event_key(row: pd.Series) -> tuple[str, str]:
    url = str(row.get("url", "")).strip()
    if url:
        return url, "exact_url"

    article_id = str(row.get("article_id", "")).strip()
    return f"article_id:{article_id}", "fallback_article_id"


def apply_source_priors(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy()

    priors = []
    roles = []
    independence_groups = []

    for _, row in result.iterrows():
        source_type = str(row.get("source_type", "")).strip()
        prior_info = SOURCE_PRIORS.get(source_type, DEFAULT_PRIOR)
        priors.append(str(prior_info["prior"]))
        roles.append(prior_info["role"])
        independence_groups.append(f"source_type:{source_type}")

    result["source_quality_prior"] = priors
    result["source_role"] = roles
    result["source_independence_group"] = independence_groups

    return result


def apply_date_flags(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy()
    today = date.today()

    result["date_quality_flag"] = result["published_date"].apply(
        lambda d: classify_date(d, today)
    )

    return result


def apply_event_keys(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy()

    keys = []
    methods = []

    for _, row in result.iterrows():
        key, method = build_event_key(row)
        keys.append(key)
        methods.append(method)

    result["event_key"] = keys
    result["event_key_method"] = methods

    return result


def apply_default_enrichment(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy()

    defaults = {
        "signal_type": "unknown",
        "signal_confidence": "",
        "orange_relevance": "REVIEW",
        "orange_relevance_confidence": "",
        "orange_fit_basis": "unsupported",
        "orange_relevance_rationale": "",
        "enrichment_method": "rules_v1",
        "enrichment_status": "needs_review",
        "review_status": "pending",
    }

    for column, default_value in defaults.items():
        if column in result.columns:
            mask = result[column].str.strip().eq("")
            result.loc[mask, column] = default_value

    return result


def enrich_rules() -> None:
    if not BASE_PATH.exists():
        raise FileNotFoundError(
            "Run --mode prepare first to create the base file."
        )

    base_data = pd.read_csv(
        BASE_PATH,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    enriched = base_data.copy()

    if ENRICHED_PATH.exists():
        existing_enriched = pd.read_csv(
            ENRICHED_PATH,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )

        for column in ENRICHMENT_COLUMNS:
            if column in existing_enriched.columns:
                enriched[column] = existing_enriched[column]

    enriched = apply_source_priors(enriched)
    enriched = apply_date_flags(enriched)
    enriched = apply_event_keys(enriched)
    enriched = apply_default_enrichment(enriched)

    ENRICHMENT_DIR.mkdir(parents=True, exist_ok=True)

    enriched.to_csv(
        ENRICHED_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"Enriched candidates: {len(enriched)} rows")
    print(f"Written: {ENRICHED_PATH}")


def import_reviewed(review_file: str) -> None:
    if not ENRICHED_PATH.exists():
        raise FileNotFoundError(
            "Run --mode enrich-rules first."
        )

    review_path = Path(review_file)

    if not review_path.exists():
        raise FileNotFoundError(
            f"Review file not found: {review_path}"
        )

    enriched = pd.read_csv(
        ENRICHED_PATH,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    reviewed = pd.read_csv(
        review_path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    if "article_id" not in reviewed.columns:
        raise ValueError("Review file must contain article_id.")

    unknown_ids = set(reviewed["article_id"]) - set(enriched["article_id"])

    if unknown_ids:
        raise ValueError(
            f"Review file contains {len(unknown_ids)} unknown article_id values. "
            "Import aborted."
        )

    review_columns = [
        "signal_type",
        "signal_confidence",
        "orange_relevance",
        "orange_relevance_confidence",
        "orange_fit_basis",
        "orange_relevance_rationale",
        "review_status",
    ]

    available_columns = [c for c in review_columns if c in reviewed.columns]

    invalid_values = {
        "orange_relevance": VALID_ORANGE_RELEVANCE,
        "orange_fit_basis": VALID_ORANGE_FIT_BASIS,
        "signal_type": VALID_SIGNAL_TYPES,
    }

    for column, allowed in invalid_values.items():
        if column in reviewed.columns:
            non_empty = reviewed[column].str.strip().ne("")
            bad = reviewed.loc[
                non_empty & ~reviewed[column].str.strip().isin(allowed),
                column,
            ]

            if not bad.empty:
                raise ValueError(
                    f"Invalid values in {column}: "
                    f"{bad.unique().tolist()}"
                )

    reviewed_indexed = reviewed.set_index("article_id")

    for column in available_columns:
        for article_id, value in reviewed_indexed[column].items():
            if str(value).strip():
                enriched.loc[
                    enriched["article_id"] == article_id,
                    column,
                ] = value

    enriched.loc[
        enriched["article_id"].isin(reviewed["article_id"]),
        "enrichment_method",
    ] = "human_review"

    has_use_case = enriched["use_case_id"].str.strip().ne("")
    has_technology = enriched["technology_id"].str.strip().ne("")
    is_relevant = enriched["orange_relevance"] == "RELEVANT"

    eligible = is_relevant & has_use_case & has_technology

    enriched.loc[
        enriched["article_id"].isin(reviewed["article_id"]) & eligible,
        "enrichment_status",
    ] = "ready_for_scoring"

    enriched.loc[
        enriched["article_id"].isin(reviewed["article_id"]) & ~eligible,
        "enrichment_status",
    ] = "needs_review"

    enriched.to_csv(
        ENRICHED_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    imported_count = len(reviewed)
    ready_count = eligible.sum()
    print(f"Imported {imported_count} reviewed records.")
    print(f"Ready for scoring: {ready_count}")
    print(f"Updated: {ENRICHED_PATH}")


def generate_summary() -> None:
    if not ENRICHED_PATH.exists():
        raise FileNotFoundError(
            "Run --mode enrich-rules first."
        )

    enriched = pd.read_csv(
        ENRICHED_PATH,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    summary_parts = []

    for column in ["vertical", "signal_type", "orange_relevance",
                    "source_role", "review_status", "enrichment_status"]:
        counts = (
            enriched[column]
            .value_counts()
            .rename_axis(column)
            .reset_index(name="count")
        )
        counts["group_by"] = column
        summary_parts.append(counts)

    summary = pd.concat(summary_parts, ignore_index=True)

    ENRICHMENT_DIR.mkdir(parents=True, exist_ok=True)

    summary.to_csv(
        SUMMARY_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    review_mask = (
        (enriched["orange_relevance"] == "REVIEW")
        | (enriched["enrichment_status"] == "needs_review")
        | (enriched["use_case_id"].str.strip().eq(""))
        | (enriched["technology_id"].str.strip().eq(""))
    )

    review_queue = enriched[review_mask].copy()
    review_queue.to_csv(
        REVIEW_QUEUE_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"Total enriched records: {len(enriched)}")
    print(f"Review queue records: {len(review_queue)}")
    print(f"Summary written: {SUMMARY_PATH}")
    print(f"Review queue written: {REVIEW_QUEUE_PATH}")


def prepare_base_file() -> None:
    if BASE_PATH.exists():
        print(
            "Base file already exists and was not overwritten: "
            f"{BASE_PATH}"
        )
        return

    candidates = load_candidate_queues()
    validate_candidates(candidates)

    base_data = add_blank_enrichment_columns(candidates)

    ENRICHMENT_DIR.mkdir(parents=True, exist_ok=True)

    base_data.to_csv(
        BASE_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"Candidate queue files: {len(find_candidate_files())}")
    print(f"Combined candidate records: {len(base_data)}")
    print(f"Written: {BASE_PATH}")


def create_review_template(limit: int) -> None:
    """Create a balanced, editable review template without overwriting work."""
    if not ENRICHED_PATH.exists():
        raise FileNotFoundError(
            "Run --mode enrich-rules first to create enriched_candidates.csv."
        )

    if limit <= 0:
        raise ValueError("--limit must be a positive integer.")

    if REVIEW_TEMPLATE_PATH.exists() and REVIEW_TEMPLATE_PATH.stat().st_size > 0:
        raise FileExistsError(
            "reviewed_enrichment.csv already contains data and will not be "
            "overwritten. Import it when review is complete, or save a new "
            "template under a different name."
        )

    enriched = pd.read_csv(
        ENRICHED_PATH,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    eligible = enriched[
        (enriched["classification_status"] == "classified")
        & enriched["use_case_id"].str.strip().ne("")
        & enriched["technology_id"].str.strip().ne("")
        & (enriched["date_quality_flag"] == "valid_past")
        & (enriched["ml_keep_recommended"] == "1")
    ].copy()

    if eligible.empty:
        raise ValueError(
            "No complete, valid-past classified candidates are available "
            "for a review template."
        )

    eligible["_source_priority"] = pd.to_numeric(
        eligible["source_quality_prior"], errors="coerce"
    ).fillna(0.0)
    eligible["_ml_priority"] = pd.to_numeric(
        eligible["ml_usefulness_probability"], errors="coerce"
    ).fillna(0.0)
    eligible = eligible.sort_values(
        ["_source_priority", "_ml_priority", "classification_confidence"],
        ascending=[False, False, False],
    )

    verticals = sorted(eligible["vertical"].unique())
    per_vertical = max(1, limit // len(verticals))
    selected_parts = []

    for vertical in verticals:
        vertical_rows = eligible[eligible["vertical"] == vertical]
        selected_parts.append(vertical_rows.head(per_vertical))

    selected = pd.concat(selected_parts, ignore_index=True)
    selected = selected.drop_duplicates(subset=["article_id"])

    if len(selected) < limit:
        selected_ids = set(selected["article_id"])
        additional = eligible[
            ~eligible["article_id"].isin(selected_ids)
        ].head(limit - len(selected))
        selected = pd.concat([selected, additional], ignore_index=True)

    selected = selected.head(limit).copy()

    template = selected.reindex(columns=REVIEW_TEMPLATE_COLUMNS, fill_value="")
    for column in [
        "signal_type",
        "signal_confidence",
        "orange_relevance",
        "orange_relevance_confidence",
        "orange_fit_basis",
        "orange_relevance_rationale",
        "review_status",
    ]:
        template[column] = ""

    ENRICHMENT_DIR.mkdir(parents=True, exist_ok=True)
    template.to_csv(
        REVIEW_TEMPLATE_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"Eligible complete candidates: {len(eligible)}")
    print(f"Review template records: {len(template)}")
    print(f"Written: {REVIEW_TEMPLATE_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich Innovation Radar candidate evidence."
    )

    parser.add_argument(
        "--mode",
        choices=[
            "prepare",
            "enrich-rules",
            "create-review-template",
            "import-reviewed",
            "summary",
        ],
        required=True,
    )

    parser.add_argument(
        "--review-file",
        type=str,
        default=None,
        help="Path to reviewed enrichment CSV (used with import-reviewed).",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=70,
        help="Template size for create-review-template (default: 70).",
    )

    arguments = parser.parse_args()

    if arguments.mode == "prepare":
        prepare_base_file()
    elif arguments.mode == "enrich-rules":
        enrich_rules()
    elif arguments.mode == "create-review-template":
        create_review_template(arguments.limit)
    elif arguments.mode == "import-reviewed":
        if not arguments.review_file:
            parser.error(
                "--review-file is required for import-reviewed mode."
            )
        import_reviewed(arguments.review_file)
    elif arguments.mode == "summary":
        generate_summary()


if __name__ == "__main__":
    main()
