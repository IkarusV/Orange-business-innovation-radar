"""Extract transparent comparable-contract observations for market sizing.

The script reads the local research database in read-only mode and links TED
procurement records to already-scored opportunity spaces.  It deliberately
does not turn tender values into euros or annual values when the database does
not contain a currency or contract duration.  Those limitations are written to
the outputs so they cannot be hidden in the UX.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd


ANALYSIS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = ANALYSIS_DIR.parent
DATABASE_PATH = PROJECT_DIR / "BeCode_dataOrange-radar-research-pipeline" / "data" / "articles_analysis.db"
SCORING_INPUT_PATH = ANALYSIS_DIR / "outputs" / "enrichment" / "auto_scoring_candidates.csv"
OUTPUT_DIR = ANALYSIS_DIR / "reference" / "market_sizing"

MIN_AWARDED_OBSERVATIONS = 5


def read_scoring_taxonomy() -> pd.DataFrame:
    """Load the taxonomy mapping used by the scoring workflow."""
    if not SCORING_INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Missing scoring input: {SCORING_INPUT_PATH}. "
            "Run 04b_auto_enrich_candidates.py first."
        )
    data = pd.read_csv(SCORING_INPUT_PATH, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    required = {"article_id", "vertical", "use_case_id", "technology_id"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError("Scoring input is missing columns: " + ", ".join(sorted(missing)))
    data = data[list(required)].copy()
    # A comparable must belong to a complete opportunity space.  Incomplete
    # taxonomy may remain useful for a review queue but cannot support a value
    # estimate for Vertical x Use Case x Technology.
    data = data[
        data["vertical"].str.strip().ne("")
        & data["use_case_id"].str.strip().ne("")
        & data["technology_id"].str.strip().ne("")
    ].copy()
    data["article_id"] = pd.to_numeric(data["article_id"], errors="coerce")
    return data.dropna(subset=["article_id"]).drop_duplicates("article_id")


def read_ted_values() -> pd.DataFrame:
    """Read TED metadata only; the SQLite database remains unchanged."""
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(f"Research database not found: {DATABASE_PATH}")
    query = """
        SELECT id AS article_id, source_name, source_type, title, url,
               published_date, extra
        FROM articles
        WHERE source_type = 'ted'
    """
    connection = sqlite3.connect(f"file:{DATABASE_PATH.resolve()}?mode=ro", uri=True)
    try:
        raw = pd.read_sql_query(query, connection)
    finally:
        connection.close()

    metadata = raw["extra"].map(lambda value: json.loads(value) if value else {})
    raw["total_contract_value_raw"] = metadata.map(lambda item: item.get("total_value"))
    raw["notice_type"] = metadata.map(lambda item: item.get("notice_type"))
    raw["buyer_country"] = metadata.map(lambda item: item.get("buyer_country"))
    raw["cpv_codes"] = metadata.map(lambda item: "; ".join(map(str, item.get("cpv") or [])))
    raw["deadline"] = metadata.map(lambda item: item.get("deadline"))
    raw["total_contract_value_raw"] = pd.to_numeric(raw["total_contract_value_raw"], errors="coerce")
    return raw.drop(columns="extra")


def classify_observation(row: pd.Series) -> pd.Series:
    """State exactly what can and cannot be inferred from the stored fields."""
    notice_type = str(row.get("notice_type") or "")
    positive_value = pd.notna(row.get("total_contract_value_raw")) and row["total_contract_value_raw"] > 0
    is_award = notice_type.startswith("can-")

    if not positive_value:
        value_status = "excluded_no_positive_value"
    elif not is_award:
        value_status = "demand_signal_only_not_awarded"
    else:
        value_status = "award_value_requires_currency_validation"

    return pd.Series({
        "is_award_notice": is_award,
        "value_observation_status": value_status,
        "currency_status": "not_collected_in_source_database",
        "annualisation_status": "not_available_contract_duration_not_collected",
        "comparability_note": (
            "Taxonomy-linked TED observation. Validate scope, currency and contract duration "
            "before using it as a comparable annual engagement value."
        ),
    })


def summarise_awards(observations: pd.DataFrame) -> pd.DataFrame:
    """Summarise raw award values without falsely assigning a currency."""
    awards = observations[
        (observations["is_award_notice"])
        & (observations["total_contract_value_raw"].notna())
        & (observations["total_contract_value_raw"] > 0)
    ].copy()
    group_columns = ["vertical", "use_case_id", "technology_id"]
    if awards.empty:
        return pd.DataFrame(columns=group_columns + [
            "awarded_observation_count", "raw_value_p25", "raw_value_median",
            "raw_value_p75", "assumption_template_status", "review_status",
        ])

    summary = awards.groupby(group_columns, as_index=False).agg(
        awarded_observation_count=("article_id", "nunique"),
        raw_value_p25=("total_contract_value_raw", lambda values: values.quantile(0.25)),
        raw_value_median=("total_contract_value_raw", "median"),
        raw_value_p75=("total_contract_value_raw", lambda values: values.quantile(0.75)),
    )
    summary["assumption_template_status"] = summary["awarded_observation_count"].map(
        lambda count: "eligible_for_manual_validation" if count >= MIN_AWARDED_OBSERVATIONS else "insufficient_awarded_observations"
    )
    summary["review_status"] = "required_currency_scope_and_duration_validation"
    return summary.sort_values(["awarded_observation_count", "vertical"], ascending=[False, True])


def make_assumption_template(summary: pd.DataFrame) -> pd.DataFrame:
    """Create only evidence-supported review rows; never invent contract values."""
    eligible = summary[summary["assumption_template_status"] == "eligible_for_manual_validation"].copy()
    columns = [
        "vertical", "use_case_id", "technology_id", "awarded_observation_count",
        "raw_value_p25", "raw_value_median", "raw_value_p75",
        "greenfield_low_annual_value_eur", "greenfield_central_annual_value_eur",
        "greenfield_high_annual_value_eur", "expansion_low_annual_value_eur",
        "expansion_central_annual_value_eur", "expansion_high_annual_value_eur",
        "currency", "basis", "method", "source_reference", "review_status", "reviewer_notes",
    ]
    template = eligible.reindex(columns=columns)
    annual_value_columns = [
        "greenfield_low_annual_value_eur", "greenfield_central_annual_value_eur",
        "greenfield_high_annual_value_eur", "expansion_low_annual_value_eur",
        "expansion_central_annual_value_eur", "expansion_high_annual_value_eur",
    ]
    template[annual_value_columns] = ""
    # EUR is a mandatory, explicit input before a value can be shown in EUR.
    template["currency"] = ""
    template["basis"] = "TED awarded comparable contracts; currency and duration must be validated"
    template["method"] = "Validate separate greenfield and expansion annual EUR values; report P25 / median / P75 for each segment"
    template["source_reference"] = "Analysis/reference/market_sizing/comparable_contract_observations.csv"
    template["review_status"] = "required"
    template["reviewer_notes"] = ""
    return template


def main() -> None:
    taxonomy = read_scoring_taxonomy()
    ted_values = read_ted_values()
    observations = taxonomy.merge(ted_values, on="article_id", how="inner", validate="one_to_one")
    classifications = observations.apply(classify_observation, axis=1)
    observations = pd.concat([observations, classifications], axis=1)
    summary = summarise_awards(observations)
    template = make_assumption_template(summary)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    observation_path = OUTPUT_DIR / "comparable_contract_observations.csv"
    summary_path = OUTPUT_DIR / "comparable_contract_summary.csv"
    template_path = OUTPUT_DIR / "annual_engagement_value_assumptions_template.csv"
    observations.to_csv(observation_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    template.to_csv(template_path, index=False, encoding="utf-8-sig")

    awarded = observations[observations["is_award_notice"] & observations["total_contract_value_raw"].gt(0)]
    print(f"Taxonomy-linked TED observations: {len(observations)}")
    print(f"Awarded notices with a positive raw value: {len(awarded)}")
    print(f"Opportunity spaces with awarded evidence: {len(summary)}")
    print(f"Spaces eligible for manual value validation (n >= {MIN_AWARDED_OBSERVATIONS}): {len(template)}")
    print(f"Written: {observation_path}")
    print(f"Written: {summary_path}")
    print(f"Written: {template_path}")
    print("Database was opened in read-only mode. No records were modified.")


if __name__ == "__main__":
    main()
