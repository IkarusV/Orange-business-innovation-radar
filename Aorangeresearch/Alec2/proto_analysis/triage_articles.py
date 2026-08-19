import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_FILE = SCRIPT_DIR / "rss_digest_v2.csv"
OUTPUT_FILE = SCRIPT_DIR / "market_intelligence_data" / "triage_results.csv"
TAXONOMY_DIR = SCRIPT_DIR / "taxonomy"

RESULT_FIELDS = [
    "article_guid",
    "article_link",
    "title",
    "source",
    "source_category",
    "independence_group",
    "source_quality_default",
    "published",
    "classification",
    "triage_confidence",
    "signal_type",
    "vertical_id",
    "use_case_id",
    "technology_id",
    "rationale",
    "prompt_version",
    "model",
    "review_status",
    "processed_at",
]


def load_ids(filename, id_column):
    with open(TAXONOMY_DIR / filename, newline="", encoding="utf-8") as file:
        return {
            row[id_column]
            for row in csv.DictReader(file)
            if row["status"] == "approved"
        }


def load_taxonomy():
    return {
        "signal_types": load_ids("signal_types.csv", "signal_type_id"),
        "verticals": load_ids("verticals.csv", "vertical_id"),
        "use_cases": load_ids("use_cases.csv", "use_case_id"),
        "technologies": load_ids("technologies.csv", "technology_id"),
    }


def load_existing_guids():
    if not OUTPUT_FILE.exists():
        return set()

    with open(OUTPUT_FILE, newline="", encoding="utf-8") as file:
        return {
            row["article_guid"]
            for row in csv.DictReader(file)
            if row["article_guid"]
        }


def validate_result(result, taxonomy):
    allowed_classifications = {"RELEVANT", "IRRELEVANT", "REVIEW"}
    allowed_confidence = {"HIGH", "MEDIUM", "LOW"}

    if result["classification"] not in allowed_classifications:
        raise ValueError("Invalid classification")

    if result["triage_confidence"] not in allowed_confidence:
        raise ValueError("Invalid triage confidence")

    checks = {
        "signal_type": taxonomy["signal_types"],
        "vertical_id": taxonomy["verticals"],
        "use_case_id": taxonomy["use_cases"],
        "technology_id": taxonomy["technologies"],
    }

    for field, allowed_ids in checks.items():
        value = result.get(field, "")
        if value and value not in allowed_ids:
            raise ValueError(f"Unknown {field}: {value}")


def classify_article(article, taxonomy):
    # Replace this function with the selected AI-provider call.
    # The model must return canonical IDs, not free-text labels.
    raise NotImplementedError(
        "Connect the selected AI model and prompt_triage_rss_orange_radar.md here."
    )


def build_result(article, result):
    return {
        "article_guid": article["guid"],
        "article_link": article["link"],
        "title": article["title"],
        "source": article["source"],
        "source_category": article["source_category"],
        "independence_group": article["independence_group"],
        "source_quality_default": article["source_quality_default"],
        "published": article["published"],
        "classification": result["classification"],
        "triage_confidence": result["triage_confidence"],
        "signal_type": result.get("signal_type", ""),
        "vertical_id": result.get("vertical_id", ""),
        "use_case_id": result.get("use_case_id", ""),
        "technology_id": result.get("technology_id", ""),
        "rationale": result["rationale"],
        "prompt_version": "1.0",
        "model": result["model"],
        "review_status": "pending_review",
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    taxonomy = load_taxonomy()
    processed_guids = load_existing_guids()

    with open(INPUT_FILE, newline="", encoding="utf-8") as file:
        articles = list(csv.DictReader(file))

    pending_articles = [
        article for article in articles
        if article["guid"] not in processed_guids
    ]

    if args.limit:
        pending_articles = pending_articles[:args.limit]

    output_exists = OUTPUT_FILE.exists()
    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=RESULT_FIELDS)

        if not output_exists:
            writer.writeheader()

        for article in pending_articles:
            result = classify_article(article, taxonomy)
            validate_result(result, taxonomy)
            writer.writerow(build_result(article, result))


if __name__ == "__main__":
    main()