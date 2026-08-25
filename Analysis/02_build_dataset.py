from pathlib import Path
import csv
import json
import re
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = Path(__file__).resolve().parent

CONFIG_PATH = ANALYSIS_DIR / "analysis_config.json"

PIPELINE_ROOT = (
    PROJECT_ROOT
    / "BeCode_dataOrange-radar-research-pipeline"
)

DB_PATH = (
    PIPELINE_ROOT
    / "data"
    / "articles_analysis.db"
)

OUTPUT_DIR = ANALYSIS_DIR / "outputs"

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Configuration not found: {CONFIG_PATH}"
        )

    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)

def get_available_verticals(
    connection: sqlite3.Connection,
) -> list[str]:

    rows = connection.execute(
        """
        SELECT DISTINCT vertical
        FROM articles
        WHERE vertical IS NOT NULL
          AND TRIM(vertical) <> ''
        ORDER BY vertical
        """
    ).fetchall()

    return [row["vertical"] for row in rows]

def resolve_target_verticals(
    configured_verticals: list[str],
    available_verticals: list[str],
) -> list[str]:

    if "*" in configured_verticals:
        return available_verticals

    unknown_verticals = sorted(
        set(configured_verticals)
        - set(available_verticals)
    )

    if unknown_verticals:
        raise ValueError(
            "Unknown verticals in configuration: "
            + ", ".join(unknown_verticals)
        )

    return configured_verticals

def load_vertical_articles(
    connection: sqlite3.Connection,
    vertical: str,
) -> list[sqlite3.Row]:

    return connection.execute(
        """
        SELECT
            articles.id AS article_id,
            articles.vertical,
            articles.title,
            articles.summary,
            articles.url,
            articles.source_name,
            articles.source_type,
            articles.published_date,
            articles.time_window,

            classifications.status
                AS classification_status,
            classifications.use_case_id,
            classifications.technology_id,
            classifications.confidence
                AS classification_confidence,
            classifications.evidence
                AS classification_evidence,

            scores.usefulness_prob
                AS ml_usefulness_probability,
            scores.keep_recommended
                AS ml_keep_recommended

        FROM articles

        LEFT JOIN article_classifications AS classifications
          ON classifications.article_id = articles.id

        LEFT JOIN ml_noise_scores AS scores
          ON scores.article_id = articles.id

        WHERE articles.vertical = ?

        ORDER BY articles.published_date DESC
        """,
        (vertical,),
    ).fetchall()

def connect_read_only() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}"
        )

    connection = sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro",
        uri=True,
    )

    connection.row_factory = sqlite3.Row
    return connection

def vertical_slug(vertical: str) -> str:
    slug = vertical.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")

def write_csv(
    output_path: Path,
    rows: list[sqlite3.Row],
) -> None:

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not rows:
        print(f"No rows for: {output_path}")
        return

    column_names = list(rows[0].keys())

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=column_names,
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(dict(row))

    print(f"Written: {output_path} ({len(rows)} rows)")

def export_vertical_dataset(
    vertical: str,
    rows: list[sqlite3.Row],
    config: dict,
) -> dict:

    allowed_sources = set(
        config["source_types"]
    )

    filtered_rows = [
        row
        for row in rows
        if row["source_type"] in allowed_sources
    ]

    candidate_statuses = set(
        config["candidate_statuses"]
    )

    candidate_rows = [
        row
        for row in filtered_rows
        if (
            row["classification_status"]
            in candidate_statuses
        )
        or (
            config.get(
                "include_unclassified",
                False,
            )
            and row["classification_status"] is None
        )
    ]

    slug = vertical_slug(vertical)

    if config.get(
        "separate_output_per_vertical",
        True,
    ):
        vertical_output = OUTPUT_DIR / slug
        articles_path = vertical_output / "articles.csv"
        candidates_path = (
            vertical_output
            / "candidate_queue.csv"
        )
    else:
        articles_path = (
            OUTPUT_DIR
            / f"{slug}_articles.csv"
        )
        candidates_path = (
            OUTPUT_DIR
            / f"{slug}_candidate_queue.csv"
        )

    write_csv(articles_path, filtered_rows)
    write_csv(candidates_path, candidate_rows)

    return {
        "vertical": vertical,
        "articles": len(filtered_rows),
        "candidates": len(candidate_rows),
    }
def validate_config(config: dict) -> None:
    required_keys = {
        "target_verticals",
        "candidate_statuses",
        "source_types",
    }

    missing_keys = required_keys - set(config)

    if missing_keys:
        raise ValueError(
            "Missing configuration keys: "
            + ", ".join(sorted(missing_keys))
        )

    if not config["target_verticals"]:
        raise ValueError(
            "target_verticals cannot be empty"
        )

    if not config["source_types"]:
        raise ValueError(
            "source_types cannot be empty"
        )

def main() -> None:
    config = load_config()
    validate_config(config)

    print(f"Database: {DB_PATH}")
    print(f"Configuration: {CONFIG_PATH}")

    summaries = []

    with connect_read_only() as connection:
        available_verticals = get_available_verticals(
            connection
        )

        target_verticals = resolve_target_verticals(
            config["target_verticals"],
            available_verticals,
        )

        print(
            "Selected verticals: "
            + ", ".join(target_verticals)
        )

        for vertical in target_verticals:
            rows = load_vertical_articles(
                connection,
                vertical,
            )

            summary = export_vertical_dataset(
                vertical=vertical,
                rows=rows,
                config=config,
            )

            summaries.append(summary)

    print()
    print("BUILD SUMMARY")
    print("=" * 70)

    for summary in summaries:
        print(
            f"{summary['vertical']}: "
            f"{summary['articles']} articles, "
            f"{summary['candidates']} candidates"
        )

    print()
    print("Database was opened in read-only mode.")


if __name__ == "__main__":
    main()