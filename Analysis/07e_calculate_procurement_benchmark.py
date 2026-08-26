"""Summarise observed TED procurement evidence without treating it as market size.

The benchmark is intentionally separate from the Step 4 bottom-up annual
potential model.  It reports published/awarded comparable notices and raw
stored values, while keeping the current source's currency and duration gaps
visible.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd


ANALYSIS_DIR = Path(__file__).resolve().parent
OBSERVATIONS_PATH = ANALYSIS_DIR / "reference" / "market_sizing" / "comparable_contract_observations.csv"
SCORES_PATH = ANALYSIS_DIR / "outputs" / "scoring" / "opportunity_scores.csv"
OUTPUT_DIR = ANALYSIS_DIR / "outputs" / "market_sizing"
RECENT_DAYS = 730


def read_required_csv(path: Path, required: set[str]) -> pd.DataFrame:
    """Read one CSV and provide a clear error if a prior step was not run."""
    if not path.exists():
        raise FileNotFoundError(f"Required input is missing: {path}")
    data = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"{path.name} is missing columns: " + ", ".join(sorted(missing)))
    return data


def summarise_observations(observations: pd.DataFrame) -> pd.DataFrame:
    """Calculate procurement evidence statistics per complete opportunity space."""
    group_columns = ["vertical", "use_case_id", "technology_id"]
    observations = observations.copy()
    observations["published_date"] = pd.to_datetime(observations["published_date"], errors="coerce", utc=True)
    observations["total_contract_value_raw"] = pd.to_numeric(observations["total_contract_value_raw"], errors="coerce")
    cutoff = pd.Timestamp(date.today(), tz="UTC") - pd.Timedelta(days=RECENT_DAYS)
    observations["is_award_notice"] = observations["is_award_notice"].str.strip().str.lower().eq("true")
    observations["is_recent"] = observations["published_date"].ge(cutoff)
    observations["has_positive_raw_value"] = observations["total_contract_value_raw"].gt(0)
    observations["awarded_positive_raw_value"] = observations["is_award_notice"] & observations["has_positive_raw_value"]

    counts = observations.groupby(group_columns, as_index=False).agg(
        ted_notice_count=("article_id", "nunique"),
        awarded_notice_count=("is_award_notice", "sum"),
        notices_with_positive_raw_value=("has_positive_raw_value", "sum"),
        awarded_notices_with_positive_raw_value=("awarded_positive_raw_value", "sum"),
        recent_notice_count=("is_recent", "sum"),
        most_recent_notice_date=("published_date", "max"),
    )
    awards = observations[observations["awarded_positive_raw_value"]].copy()
    if awards.empty:
        values = pd.DataFrame(columns=group_columns + ["raw_award_value_p25", "raw_award_value_median", "raw_award_value_p75"])
    else:
        values = awards.groupby(group_columns, as_index=False).agg(
            raw_award_value_p25=("total_contract_value_raw", lambda x: x.quantile(0.25)),
            raw_award_value_median=("total_contract_value_raw", "median"),
            raw_award_value_p75=("total_contract_value_raw", lambda x: x.quantile(0.75)),
        )
    benchmark = counts.merge(values, on=group_columns, how="left")
    benchmark["procurement_benchmark_status"] = "observed_notices_no_awarded_positive_value"
    benchmark.loc[benchmark["awarded_notices_with_positive_raw_value"].gt(0), "procurement_benchmark_status"] = "raw_award_values_currency_and_duration_unvalidated"
    benchmark["currency_status"] = "not_collected_in_source_database"
    benchmark["annualisation_status"] = "not_available_contract_duration_not_collected"
    benchmark["benchmark_interpretation"] = (
        "Observed taxonomy-linked TED procurement evidence only; do not add to annual market potential "
        "or present raw values as EUR until currency and duration are validated."
    )
    return benchmark


def calculate_benchmark() -> pd.DataFrame:
    """Retain all scored spaces, including those with no linked TED evidence."""
    scores = read_required_csv(
        SCORES_PATH,
        {"opportunity_id", "vertical", "use_case_id", "technology_id", "priority_score", "evidence_count"},
    )
    observations = read_required_csv(
        OBSERVATIONS_PATH,
        {"article_id", "vertical", "use_case_id", "technology_id", "published_date", "is_award_notice", "total_contract_value_raw"},
    )
    observed = summarise_observations(observations)
    result = scores.merge(observed, on=["vertical", "use_case_id", "technology_id"], how="left")
    count_columns = [
        "ted_notice_count", "awarded_notice_count", "notices_with_positive_raw_value",
        "awarded_notices_with_positive_raw_value", "recent_notice_count",
    ]
    for column in count_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0).astype(int)
    result["procurement_benchmark_status"] = result["procurement_benchmark_status"].fillna("no_taxonomy_linked_ted_observation")
    result["currency_status"] = result["currency_status"].fillna("not_applicable_no_ted_value")
    result["annualisation_status"] = result["annualisation_status"].fillna("not_applicable_no_ted_value")
    result["benchmark_interpretation"] = result["benchmark_interpretation"].fillna(
        "No taxonomy-linked TED observation in the current scoring-ready corpus."
    )
    return result.sort_values(["awarded_notices_with_positive_raw_value", "priority_score"], ascending=[False, False])


def main() -> None:
    benchmark = calculate_benchmark()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    benchmark_path = OUTPUT_DIR / "procurement_benchmark.csv"
    summary_path = OUTPUT_DIR / "procurement_benchmark_summary.csv"
    benchmark.to_csv(benchmark_path, index=False, encoding="utf-8-sig")
    summary = benchmark.groupby("procurement_benchmark_status", as_index=False).agg(
        opportunity_spaces=("opportunity_id", "nunique"),
        ted_notice_count=("ted_notice_count", "sum"),
        awarded_positive_value_notices=("awarded_notices_with_positive_raw_value", "sum"),
    )
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    print(f"Benchmark opportunity spaces: {benchmark['opportunity_id'].nunique()}")
    print(summary.to_string(index=False))
    print(f"Written: {benchmark_path}")
    print(f"Written: {summary_path}")


if __name__ == "__main__":
    main()
