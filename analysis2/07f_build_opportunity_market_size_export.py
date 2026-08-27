"""Build a Beta-app-friendly market-size export by opportunity space.

The output has one record per Vertical x Use Case x Technology. Europe is the
headline scope; Orange Business regions are retained as optional drill-downs.
Only scenario rows that passed the Step 4 validation gate contribute EUR
values. The script never asks an LLM to calculate or fill a missing number.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ANALYSIS_DIR = Path(__file__).resolve().parent
INPUT_PATH = ANALYSIS_DIR / "outputs" / "market_sizing" / "market_potential_scenarios.csv"
OUTPUT_DIR = ANALYSIS_DIR / "outputs" / "market_sizing"
JSON_PATH = OUTPUT_DIR / "beta_opportunity_market_sizes.json"
CSV_PATH = OUTPUT_DIR / "beta_opportunity_market_sizes.csv"

KEY_COLUMNS = ["vertical", "use_case_id", "technology_id"]
SCENARIOS = ["greenfield", "expansion_or_managed_service"]


def opportunity_key(vertical: str, use_case_id: str, technology_id: str) -> str:
    """Build the same stable taxonomy key the Beta-app can reproduce."""
    return "|".join([vertical.strip(), use_case_id.strip(), technology_id.strip()])


def load_scenarios() -> pd.DataFrame:
    """Load Step 4 and normalise numeric fields used in the export."""
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Run 07d_calculate_market_potential.py first: {INPUT_PATH}")
    data = pd.read_csv(INPUT_PATH, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    required = set(KEY_COLUMNS + [
        "demand_scenario", "geography_level", "geography_id", "geography_label",
        "nace_codes", "vertical_mapping_status", "vertical_mapping_quality",
        "vertical_statistical_scope", "vertical_mapping_limitation",
        "denominator_method", "technology_proxy", "technology_mapping_status",
        "market_potential_status", "validation_status", "countries_with_source_data",
        "expected_country_count", "country_coverage_ratio", "country_coverage_status",
        "nace_component_coverage_ratio", "nace_component_coverage_status",
        "public_employment_persons", "general_public_services_expenditure_eur",
        "defence_expenditure_eur", "linked_ted_notice_count",
        "addressable_enterprise_base", "low_annual_potential_eur",
        "central_annual_potential_eur", "high_annual_potential_eur",
    ])
    missing = required - set(data.columns)
    if missing:
        raise ValueError("Market scenario input is missing columns: " + ", ".join(sorted(missing)))
    numeric = [
        "countries_with_source_data", "expected_country_count", "country_coverage_ratio",
        "nace_component_coverage_ratio",
        "addressable_enterprise_base", "low_annual_potential_eur",
        "central_annual_potential_eur", "high_annual_potential_eur",
        "public_employment_persons", "general_public_services_expenditure_eur",
        "defence_expenditure_eur", "linked_ted_notice_count",
    ]
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data


def scenario_payload(row: pd.Series | None) -> dict:
    """Convert one validated or blocked scenario row to a serialisable record."""
    if row is None:
        return {
            "status": "unavailable",
            "validation_status": "missing_scenario",
            "addressable_enterprise_base": None,
            "low_eur": None,
            "central_eur": None,
            "high_eur": None,
        }
    passed = (
        row["validation_status"] == "passed"
        and str(row["market_potential_status"]).startswith("estimated_")
    )
    return {
        "status": "estimated" if passed else row["market_potential_status"],
        "validation_status": row["validation_status"],
        "addressable_enterprise_base": float(row["addressable_enterprise_base"]) if pd.notna(row["addressable_enterprise_base"]) else None,
        "low_eur": float(row["low_annual_potential_eur"]) if passed and pd.notna(row["low_annual_potential_eur"]) else None,
        "central_eur": float(row["central_annual_potential_eur"]) if passed and pd.notna(row["central_annual_potential_eur"]) else None,
        "high_eur": float(row["high_annual_potential_eur"]) if passed and pd.notna(row["high_annual_potential_eur"]) else None,
    }


def geography_payload(rows: pd.DataFrame) -> dict:
    """Combine the two non-overlapping demand segments for one geography."""
    first = rows.iloc[0]
    scenario_names = (
        ["active_public_procurement"]
        if first["denominator_method"] == "public_buyer_count"
        else SCENARIOS
    )
    by_scenario = {
        scenario: scenario_payload(
            rows[rows["demand_scenario"] == scenario].iloc[0]
            if not rows[rows["demand_scenario"] == scenario].empty else None
        )
        for scenario in scenario_names
    }
    segments = list(by_scenario.values())
    estimated_segments = [segment for segment in segments if segment["status"] == "estimated"]
    if len(estimated_segments) == len(scenario_names):
        status = "estimated"
    elif estimated_segments:
        status = "partial_estimate"
    else:
        status = "pending_or_unavailable"

    def total(field: str) -> float | None:
        return sum(segment[field] for segment in estimated_segments) if len(estimated_segments) == len(scenario_names) else None

    return {
        "status": status,
        "low_eur": total("low_eur"),
        "central_eur": total("central_eur"),
        "high_eur": total("high_eur"),
        "countries_covered": int(first["countries_with_source_data"]) if pd.notna(first["countries_with_source_data"]) else 0,
        "countries_expected": int(first["expected_country_count"]) if pd.notna(first["expected_country_count"]) else 0,
        "coverage_ratio": float(first["country_coverage_ratio"]) if pd.notna(first["country_coverage_ratio"]) else 0.0,
        "coverage_status": first["country_coverage_status"],
        "nace_component_coverage_ratio": float(first["nace_component_coverage_ratio"]) if pd.notna(first["nace_component_coverage_ratio"]) else 0.0,
        "nace_component_coverage_status": first["nace_component_coverage_status"],
        "public_employment_persons": float(first["public_employment_persons"]) if pd.notna(first["public_employment_persons"]) else None,
        "general_public_services_expenditure_eur": float(first["general_public_services_expenditure_eur"]) if pd.notna(first["general_public_services_expenditure_eur"]) else None,
        "defence_expenditure_eur": float(first["defence_expenditure_eur"]) if pd.notna(first["defence_expenditure_eur"]) else None,
        "linked_ted_notice_count": int(first["linked_ted_notice_count"]) if pd.notna(first["linked_ted_notice_count"]) else 0,
        "blocking_reasons": sorted({
            segment["validation_status"]
            for segment in segments
            if segment["status"] != "estimated"
        }),
        "segments": by_scenario,
    }


def build_export(data: pd.DataFrame) -> tuple[list[dict], pd.DataFrame]:
    """Return nested JSON records and a flat one-row-per-opportunity table."""
    records: list[dict] = []
    flat_rows: list[dict] = []
    for key, group in data.groupby(KEY_COLUMNS, sort=True):
        vertical, use_case_id, technology_id = key
        europe_rows = group[group["geography_level"] == "europe"]
        europe = geography_payload(europe_rows) if not europe_rows.empty else {
            "status": "unavailable", "low_eur": None, "central_eur": None, "high_eur": None,
            "countries_covered": 0, "countries_expected": 0, "coverage_ratio": 0.0,
            "coverage_status": "no_country_data", "nace_component_coverage_ratio": 0.0,
            "nace_component_coverage_status": "no_component_data",
            "public_employment_persons": None,
            "general_public_services_expenditure_eur": None,
            "defence_expenditure_eur": None,
            "linked_ted_notice_count": 0,
            "blocking_reasons": ["missing_europe_scenario"], "segments": {},
        }
        regions = []
        regional = group[group["geography_level"] == "region"]
        for (region_id, region_label), region_rows in regional.groupby(["geography_id", "geography_label"], sort=True):
            regions.append({
                "region_id": region_id,
                "region_label": region_label,
                **geography_payload(region_rows),
            })
        stable_key = opportunity_key(vertical, use_case_id, technology_id)
        first = group.iloc[0]
        mapping = {
            "nace_codes": [code for code in first["nace_codes"].split(";") if code],
            "denominator_method": first["denominator_method"],
            "vertical_mapping_status": first["vertical_mapping_status"],
            "vertical_mapping_quality": first["vertical_mapping_quality"],
            "vertical_statistical_scope": first["vertical_statistical_scope"],
            "vertical_mapping_limitation": first["vertical_mapping_limitation"],
            "technology_proxy": first["technology_proxy"],
            "technology_mapping_status": first["technology_mapping_status"],
        }
        records.append({
            "opportunity_key": stable_key,
            "vertical": vertical,
            "use_case_id": use_case_id,
            "technology_id": technology_id,
            "market_size": europe,
            "statistical_mapping": mapping,
            "regional_breakdown": regions,
            "display_rule": "Show EUR only when market_size.status is estimated; otherwise show its evidence-gap status.",
        })
        flat_rows.append({
            "opportunity_key": stable_key,
            "vertical": vertical,
            "use_case_id": use_case_id,
            "technology_id": technology_id,
            "market_size_status": europe["status"],
            "europe_low_eur": europe["low_eur"],
            "europe_central_eur": europe["central_eur"],
            "europe_high_eur": europe["high_eur"],
            "countries_covered": europe["countries_covered"],
            "countries_expected": europe["countries_expected"],
            "coverage_ratio": europe["coverage_ratio"],
            "coverage_status": europe["coverage_status"],
            "nace_component_coverage_ratio": europe["nace_component_coverage_ratio"],
            "nace_component_coverage_status": europe["nace_component_coverage_status"],
            "blocking_reasons": ";".join(europe["blocking_reasons"]),
            "public_employment_persons": europe["public_employment_persons"],
            "general_public_services_expenditure_eur": europe["general_public_services_expenditure_eur"],
            "defence_expenditure_eur": europe["defence_expenditure_eur"],
            "linked_ted_notice_count": europe["linked_ted_notice_count"],
            **mapping,
        })
    return records, pd.DataFrame(flat_rows)


def main() -> None:
    data = load_scenarios()
    records, flat = build_export(data)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    flat.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    print(f"Opportunity-space market-size records: {len(records)}")
    print(flat["market_size_status"].value_counts(dropna=False).to_string())
    print(f"Written: {JSON_PATH}")
    print(f"Written: {CSV_PATH}")


if __name__ == "__main__":
    main()
