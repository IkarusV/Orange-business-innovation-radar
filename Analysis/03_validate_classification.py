from pathlib import Path
import argparse

import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ANALYSIS_DIR / "outputs"

VALIDATION_DIR = OUTPUT_DIR / "validation"

VALIDATION_SAMPLE_PATH = (
    VALIDATION_DIR
    / "validation_sample.csv"
)

METRICS_PATH = (
    VALIDATION_DIR
    / "validation_metrics.csv"
)

CONFUSION_MATRIX_PATH = (
    VALIDATION_DIR
    / "confusion_matrix.csv"
)

RANDOM_SEED = 20260824

REQUIRED_STATUSES = [
    "classified",
    "needs_review",
    "no_match",
]

SAMPLES_PER_STRATUM = 1

PIPELINE_LABEL_MAP = {
    "classified": "RELEVANT",
    "no_match": "IRRELEVANT",
    "needs_review": "REVIEW",
}


def find_vertical_files() -> list[Path]:
    return sorted(
        OUTPUT_DIR.glob("*/articles.csv")
    )


def load_all_articles() -> pd.DataFrame:
    files = find_vertical_files()

    if not files:
        raise FileNotFoundError(
            "No vertical articles.csv files found."
        )

    datasets = []

    for file_path in files:
        dataframe = pd.read_csv(
            file_path,
            dtype=str,
            keep_default_na=False,
        )

        datasets.append(dataframe)

    return pd.concat(
        datasets,
        ignore_index=True,
    )


REQUIRED_COLUMNS = {
    "article_id",
    "vertical",
    "title",
    "summary",
    "url",
    "source_name",
    "source_type",
    "classification_status",
    "use_case_id",
    "technology_id",
    "classification_confidence",
}


def validate_columns(
    dataframe: pd.DataFrame,
) -> None:

    missing_columns = (
        REQUIRED_COLUMNS
        - set(dataframe.columns)
    )

    if missing_columns:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

def add_pipeline_labels(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    result = dataframe.copy()

    result["pipeline_prediction"] = (
        result["classification_status"]
        .map(PIPELINE_LABEL_MAP)
        .fillna("UNCLASSIFIED")
    )

    return result


def create_stratified_sample(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    sample_parts = []

    verticals = sorted(
        dataframe["vertical"]
        .dropna()
        .unique()
    )

    for vertical in verticals:
        vertical_data = dataframe[
            dataframe["vertical"] == vertical
        ]

        for status in REQUIRED_STATUSES:
            group = vertical_data[
                vertical_data["classification_status"]
                == status
            ]

            if group.empty:
                print(
                    f"Warning: no {status} records "
                    f"for {vertical}"
                )
                continue

            number_to_sample = min(
                SAMPLES_PER_STRATUM,
                len(group),
            )

            sample = group.sample(
                n=number_to_sample,
                random_state=RANDOM_SEED,
            )

            sample_parts.append(sample)

    if not sample_parts:
        raise ValueError(
            "No records matched the requested validation strata."
        )

    return pd.concat(
        sample_parts,
        ignore_index=True,
    )

def add_human_review_columns(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    result = dataframe.copy()

    result["human_taxonomy_relevance"] = ""
    result["human_mapping_quality"] = ""
    result["human_orange_relevance"] = ""
    result["human_rationale"] = ""
    result["reviewer"] = ""
    result["reviewed_at"] = ""

    return result


def write_validation_sample(
    dataframe: pd.DataFrame,
) -> None:

    VALIDATION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if VALIDATION_SAMPLE_PATH.exists():
        print(
            "Validation sample already exists and was not overwritten: "
            f"{VALIDATION_SAMPLE_PATH}"
        )
        return

    dataframe.to_csv(
        VALIDATION_SAMPLE_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print(
        f"Validation sample created: "
        f"{VALIDATION_SAMPLE_PATH}"
    )


def load_completed_sample() -> pd.DataFrame:
    if not VALIDATION_SAMPLE_PATH.exists():
        raise FileNotFoundError(
            "Create the validation sample first."
        )

    dataframe = pd.read_csv(
        VALIDATION_SAMPLE_PATH,
        dtype=str,
        keep_default_na=False,
    )

    required_sample_columns = {
        "pipeline_prediction",
        "human_taxonomy_relevance",
    }
    missing_columns = required_sample_columns - set(dataframe.columns)
    if missing_columns:
        raise ValueError(
            "Validation sample is missing columns: "
            + ", ".join(sorted(missing_columns))
        )

    dataframe["human_taxonomy_relevance"] = (
        dataframe["human_taxonomy_relevance"]
        .str.strip()
        .str.upper()
    )

    valid_labels = {
        "RELEVANT",
        "IRRELEVANT",
        "UNSURE",
        "REVIEW",
    }

    invalid = dataframe[
        ~dataframe["human_taxonomy_relevance"]
        .isin(valid_labels)
    ]

    if not invalid.empty:
        raise ValueError(
            "Complete human_taxonomy_relevance "
            "before calculating metrics."
        )

    return dataframe


def calculate_metrics(
    dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:

    evaluation_data = dataframe[
        dataframe["pipeline_prediction"].isin(
            ["RELEVANT", "IRRELEVANT"]
        )
        &
        dataframe["human_taxonomy_relevance"].isin(
            ["RELEVANT", "IRRELEVANT"]
        )
    ].copy()

    if evaluation_data.empty:
        raise ValueError(
            "No finalized RELEVANT/IRRELEVANT rows "
            "are available for evaluation."
        )

    y_true = evaluation_data[
        "human_taxonomy_relevance"
    ]

    y_pred = evaluation_data[
        "pipeline_prediction"
    ]

    precision, recall, f1, _ = (
        precision_recall_fscore_support(
            y_true,
            y_pred,
            labels=["RELEVANT"],
            average=None,
            zero_division=0,
        )
    )

    metrics = pd.DataFrame(
        [{
            "evaluation_rows": len(evaluation_data),
            "accuracy": round(
                accuracy_score(y_true, y_pred),
                3,
            ),
            "relevant_precision": round(
                precision[0],
                3,
            ),
            "relevant_recall": round(
                recall[0],
                3,
            ),
            "relevant_f1": round(
                f1[0],
                3,
            ),
            "needs_review_count": (
                dataframe["pipeline_prediction"]
                == "REVIEW"
            ).sum(),
            "human_ambiguous_count": (
                dataframe[
                    "human_taxonomy_relevance"
                ]
                .isin(["UNSURE", "REVIEW"])
            ).sum(),
        }]
    )

    matrix = confusion_matrix(
        y_true,
        y_pred,
        labels=["RELEVANT", "IRRELEVANT"],
    )

    confusion = pd.DataFrame(
        matrix,
        index=[
            "actual_relevant",
            "actual_irrelevant",
        ],
        columns=[
            "predicted_relevant",
            "predicted_irrelevant",
        ],
    )

    return metrics, confusion

REVIEW_RESOLUTION_PATH = (
    VALIDATION_DIR
    / "review_resolution.csv"
)


def save_evaluation_outputs(
    dataframe: pd.DataFrame,
    metrics: pd.DataFrame,
    confusion: pd.DataFrame,
) -> None:

    VALIDATION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    metrics.to_csv(
        METRICS_PATH,
        index=False,
    )

    confusion.to_csv(
        CONFUSION_MATRIX_PATH,
    )

    review_resolution = (
        dataframe[
            dataframe["pipeline_prediction"] == "REVIEW"
        ]
        ["human_taxonomy_relevance"]
        .value_counts()
        .rename_axis("human_label")
        .reset_index(name="count")
    )

    review_resolution.to_csv(
        REVIEW_RESOLUTION_PATH,
        index=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mode",
        choices=["create-sample", "evaluate"],
        required=True,
    )

    arguments = parser.parse_args()

    if arguments.mode == "create-sample":
        articles = load_all_articles()
        validate_columns(articles)

        articles = add_pipeline_labels(articles)

        sample = create_stratified_sample(
            articles
        )

        sample = add_human_review_columns(
            sample
        )

        write_validation_sample(sample)

        print(
            "Open validation_sample.csv, "
            "complete the human-review columns, "
            "then run --mode evaluate."
        )

    elif arguments.mode == "evaluate":
        completed_sample = load_completed_sample()

        metrics, confusion = calculate_metrics(
            completed_sample
        )

        save_evaluation_outputs(
            dataframe=completed_sample,
            metrics=metrics,
            confusion=confusion,
        )

        print(metrics.to_string(index=False))
        print()
        print(confusion.to_string())


if __name__ == "__main__":
    main()
