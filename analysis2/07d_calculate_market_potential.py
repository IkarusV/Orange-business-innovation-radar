"""Calculate evidence-bounded market-potential scenarios for opportunity spaces.

This is a transparent bottom-up model, not a revenue forecast.  It combines
official Eurostat enterprise counts and ICT-adoption proxies with an explicitly
reviewed annual engagement-value assumption.  If any required input is absent,
the output records the reason instead of fabricating a euro estimate.
"""

from __future__ import annotations

from pathlib import Path
from collections import Counter

import pandas as pd

from market_geography import load_geography
from market_verticals import load_vertical_config


ANALYSIS_DIR = Path(__file__).resolve().parent
EUROSTAT_DIR = ANALYSIS_DIR / "reference" / "eurostat"
MARKET_DIR = ANALYSIS_DIR / "reference" / "market_sizing"
SCORING_PATH = ANALYSIS_DIR / "outputs" / "scoring" / "opportunity_scores.csv"
ENTERPRISE_PATH = EUROSTAT_DIR / "enterprise_counts_standard.csv"
ADOPTION_PATH = EUROSTAT_DIR / "technology_adoption_rates.csv"
PUBLIC_CONTEXT_PATH = EUROSTAT_DIR / "public_sector" / "public_sector_country_context.csv"
PUBLIC_BUYER_PATH = EUROSTAT_DIR / "public_sector" / "public_buyer_counts_by_opportunity.csv"
ASSUMPTION_PATH = MARKET_DIR / "annual_engagement_value_assumptions_template.csv"
OUTPUT_DIR = ANALYSIS_DIR / "outputs" / "market_sizing"
TARGET_COUNTRIES, COUNTRY_TO_REGION, REGION_LABELS, MARKET_SCOPE_NAME = load_geography()
REGION_COUNTRY_COUNTS = Counter(COUNTRY_TO_REGION.values())
VERTICAL_CONFIG = load_vertical_config()

# A technology remains unmapped when the downloaded Eurostat ICT datasets do
# not provide a defensible proxy. Vertical mappings are kept in the separate,
# reviewable market_vertical_config.json file.
TECHNOLOGY_TO_PROXY = {
    "machine-learning": "ai",
    "computer-vision": "ai",
    "natural-language-processing": "ai",
    "cloud-data-platform": "cloud",
    "edge-computing": "cloud",
    "digital-twin": "cloud",
    "cybersecurity-platform": "cybersecurity",
    "iot-platforms": "iot",
    "rfid-asset-tagging": "iot",
    "industrial-robotics": "iot",
    "autonomous-vehicles-drones": "iot",
    "warehouse-automation-systems": "iot",
}


def read_required_csv(path: Path, required: set[str]) -> pd.DataFrame:
    """Read one input and fail clearly if its schema has changed."""
    if not path.exists():
        raise FileNotFoundError(f"Required input is missing: {path}")
    data = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"{path.name} is missing columns: " + ", ".join(sorted(missing)))
    return data


def prepare_opportunities() -> pd.DataFrame:
    """Attach possibly multi-code NACE scopes and ICT proxy mappings."""
    data = read_required_csv(
        SCORING_PATH,
        {"opportunity_id", "vertical", "use_case_id", "technology_id", "priority_score", "evidence_count"},
    ).copy()

    crosswalk_rows = []
    for mapping in VERTICAL_CONFIG["verticals"].values():
        is_public_buyer_method = mapping["denominator_method"] == "public_buyer_count"
        if mapping["enabled"]:
            codes = mapping["nace_codes"]
        elif is_public_buyer_method:
            codes = [mapping["public_context_nace_code"] or "O"]
        else:
            codes = [pd.NA]
        for code in codes:
            displayed_codes = (
                mapping["nace_codes"]
                if mapping["nace_codes"]
                else ([mapping["public_context_nace_code"]] if is_public_buyer_method else [])
            )
            crosswalk_rows.append({
                "vertical": mapping["vertical"],
                "nace_code": code,
                "nace_codes": ";".join(displayed_codes),
                "expected_nace_code_count": len(displayed_codes),
                "denominator_method": mapping["denominator_method"],
                "vertical_mapping_status": (
                    "mapped_public_buyer_denominator"
                    if is_public_buyer_method
                    else ("mapped" if mapping["enabled"] else mapping["mapping_quality"])
                ),
                "vertical_mapping_quality": mapping["mapping_quality"],
                "vertical_statistical_scope": mapping["statistical_scope"],
                "vertical_mapping_limitation": mapping["limitation"],
            })
    crosswalk = pd.DataFrame(crosswalk_rows)
    data = data.merge(crosswalk, on="vertical", how="left", validate="many_to_many")
    missing_config = data["vertical_mapping_status"].isna()
    data.loc[missing_config, "vertical_mapping_status"] = "not_configured"
    data.loc[missing_config, "vertical_mapping_quality"] = "not_configured"
    data.loc[missing_config, "denominator_method"] = "not_configured"
    data.loc[missing_config, "vertical_statistical_scope"] = ""
    data.loc[missing_config, "vertical_mapping_limitation"] = (
        "The radar vertical is absent from market_vertical_config.json."
    )
    data.loc[missing_config, "nace_codes"] = ""
    data.loc[missing_config, "expected_nace_code_count"] = 0

    data["technology_proxy"] = data["technology_id"].map(TECHNOLOGY_TO_PROXY)
    data["technology_mapping_status"] = data["technology_proxy"].notna().map(
        {True: "mapped_proxy", False: "no_defensible_available_ict_proxy"}
    )
    return data


def prepare_enterprise_and_adoption() -> pd.DataFrame:
    """Join country-size enterprise counts to technology-specific adoption rates."""
    enterprises = read_required_csv(
        ENTERPRISE_PATH,
        {"country", "nace_code", "size_class", "observed_value"},
    ).copy()
    adoption = read_required_csv(
        ADOPTION_PATH,
        {"technology_proxy", "country", "size_class", "adoption_rate", "basis", "proxy_reason"},
    ).copy()
    enterprises["enterprise_count"] = pd.to_numeric(enterprises["observed_value"], errors="coerce")
    adoption["adoption_rate"] = pd.to_numeric(adoption["adoption_rate"], errors="coerce")
    # A suppressed value is an availability/coverage gap, not a negative or
    # out-of-range input. Exclude unavailable cells from arithmetic so the
    # country-coverage fields report the limitation honestly.
    enterprises["enterprise_input_invalid"] = enterprises["enterprise_count"].notna() & enterprises["enterprise_count"].lt(0)
    adoption["adoption_input_invalid"] = adoption["adoption_rate"].notna() & ~adoption["adoption_rate"].between(0, 1, inclusive="both")
    enterprises = enterprises[enterprises["enterprise_count"].notna() & ~enterprises["enterprise_input_invalid"]].copy()
    adoption = adoption[adoption["adoption_rate"].notna() & ~adoption["adoption_input_invalid"]].copy()
    enterprises["enterprise_input_valid"] = True
    adoption["adoption_input_valid"] = True
    # One adoption rate is intentionally paired with each applicable NACE
    # denominator in the same country-size cell. Composite verticals are later
    # aggregated across their configured, non-overlapping component codes.
    return enterprises.merge(
        adoption, on=["country", "region", "size_class"], how="inner", validate="many_to_many"
    )


def prepare_public_buyer_inputs(public_opportunities: pd.DataFrame) -> pd.DataFrame:
    """Build one country row per public opportunity using TED buyer counts.

    NACE O employment and COFOG expenditure remain context fields. The numeric
    customer denominator is the opportunity-linked, deduplicated TED buyer
    count. Zero observed buyers is treated as an evidence gap, not zero demand.
    """
    context = read_required_csv(
        PUBLIC_CONTEXT_PATH,
        {
            "country", "region", "public_employment_persons",
            "general_public_services_expenditure_eur", "defence_expenditure_eur",
            "employment_coverage_status", "expenditure_coverage_status",
        },
    ).copy()
    buyers = read_required_csv(
        PUBLIC_BUYER_PATH,
        {
            "vertical", "use_case_id", "technology_id", "country",
            "unique_public_buyer_count", "linked_ted_notice_count",
        },
    ).copy()
    numeric_context = [
        "public_employment_persons", "general_public_services_expenditure_eur",
        "defence_expenditure_eur",
    ]
    for column in numeric_context:
        context[column] = pd.to_numeric(context[column], errors="coerce")
    buyers["unique_public_buyer_count"] = pd.to_numeric(
        buyers["unique_public_buyer_count"], errors="coerce"
    )
    buyers["linked_ted_notice_count"] = pd.to_numeric(
        buyers["linked_ted_notice_count"], errors="coerce"
    )

    keys = ["vertical", "use_case_id", "technology_id"]
    public_opportunities = public_opportunities.drop_duplicates(keys).copy()
    public_opportunities["_join"] = 1
    context["_join"] = 1
    detail = public_opportunities.merge(context, on="_join", how="inner").drop(columns="_join")
    detail = detail.merge(buyers, on=keys + ["country"], how="left")
    detail["unique_public_buyer_count"] = detail["unique_public_buyer_count"].fillna(0)
    detail["linked_ted_notice_count"] = detail["linked_ted_notice_count"].fillna(0)
    detail["enterprise_count"] = detail["unique_public_buyer_count"]
    detail["size_class"] = "public_buyer"
    detail["adoption_rate"] = 1.0
    detail["basis"] = "observed_opportunity_linked_ted_buyers"
    detail["proxy_reason"] = (
        "Observed procurement-active buyer lower bound. NACE O employment and "
        "COFOG expenditure are context only and are not multiplied into market size."
    )
    detail["enterprise_input_valid"] = True
    detail["adoption_input_valid"] = True
    detail["denominator_country"] = detail["country"].where(
        detail["unique_public_buyer_count"].gt(0)
    )
    return detail


def prepare_assumptions() -> pd.DataFrame:
    """Return one validated assumption row per opportunity and demand segment."""
    assumptions = read_required_csv(
        ASSUMPTION_PATH,
        {
            "vertical", "use_case_id", "technology_id", "review_status",
        },
    ).copy()
    if "currency" not in assumptions.columns:
        assumptions["currency"] = ""

    key_columns = ["vertical", "use_case_id", "technology_id", "currency", "review_status"]
    long_rows = []
    segment_prefixes = {
        "greenfield": "greenfield",
        "expansion_or_managed_service": "expansion",
        "active_public_procurement": "public",
    }
    for scenario, prefix in segment_prefixes.items():
        segment_columns = {
            f"{prefix}_low_annual_value_eur": "low_annual_value_eur",
            f"{prefix}_central_annual_value_eur": "central_annual_value_eur",
            f"{prefix}_high_annual_value_eur": "high_annual_value_eur",
        }
        segment = assumptions[key_columns].copy()
        for source, target in segment_columns.items():
            segment[target] = pd.to_numeric(
                assumptions[source] if source in assumptions.columns else "",
                errors="coerce",
            )
        segment["demand_scenario"] = scenario
        segment["annual_value_method"] = "scenario_specific"
        long_rows.append(segment)

    result = pd.concat(long_rows, ignore_index=True) if long_rows else pd.DataFrame()
    value_columns = ["low_annual_value_eur", "central_annual_value_eur", "high_annual_value_eur"]
    result["assumption_status"] = "not_approved"
    approved = result["review_status"].str.strip().str.lower().eq("approved")
    complete = result[value_columns].notna().all(axis=1)
    non_negative = (result[value_columns] >= 0).all(axis=1)
    ordered = (
        result["low_annual_value_eur"].le(result["central_annual_value_eur"])
        & result["central_annual_value_eur"].le(result["high_annual_value_eur"])
    )
    is_eur = result["currency"].str.strip().str.upper().eq("EUR")
    result.loc[approved & ~complete, "assumption_status"] = "approved_incomplete_values"
    result.loc[approved & complete & ~non_negative, "assumption_status"] = "invalid_negative_annual_value"
    result.loc[approved & complete & non_negative & ~ordered, "assumption_status"] = "invalid_unordered_annual_range"
    result.loc[approved & complete & non_negative & ordered & ~is_eur, "assumption_status"] = "approved_currency_not_eur"
    result.loc[approved & complete & non_negative & ordered & is_eur, "assumption_status"] = "approved_complete"
    return result


def invalid_cell_count(values: pd.Series) -> int:
    """Count false or missing validation flags without Boolean bitwise coercion."""
    return int(values.fillna(False).astype(bool).eq(False).sum())


def sum_or_missing(values: pd.Series):
    """Sum numeric context while keeping an all-missing group as missing."""
    return values.sum(min_count=1)


BASE_GROUPING = [
    "opportunity_id", "vertical", "use_case_id", "technology_id", "priority_score", "evidence_count",
    "nace_codes", "expected_nace_code_count", "denominator_method", "vertical_mapping_status",
    "vertical_mapping_quality", "vertical_statistical_scope", "vertical_mapping_limitation",
    "technology_proxy", "technology_mapping_status",
    "demand_scenario", "assumption_status", "currency", "annual_value_method",
]


def aggregate_geography(detail: pd.DataFrame, level: str) -> pd.DataFrame:
    """Aggregate country-level calculation cells into country, region or Europe."""
    work = detail.copy()
    work["nace_country_key"] = (
        work["denominator_country"].fillna("").astype(str)
        + "|"
        + work["nace_code"].fillna("").astype(str)
    )
    work.loc[
        work["denominator_country"].isna() | work["nace_code"].isna(),
        "nace_country_key",
    ] = pd.NA
    if level == "country":
        work = work[work["country"].notna()].copy()
        work["geography_id"] = work["country"]
        work["geography_label"] = work["country"]
        work["expected_country_count"] = 1
    elif level == "region":
        work = work[work["region"].notna()].copy()
        work["geography_id"] = work["region"]
        work["geography_label"] = work["region"].map(REGION_LABELS)
        work["expected_country_count"] = work["region"].map(REGION_COUNTRY_COUNTS)
    elif level == "europe":
        work["geography_id"] = "europe"
        work["geography_label"] = "Europe total (configured scope)"
        work["expected_country_count"] = len(TARGET_COUNTRIES)
    else:
        raise ValueError(f"Unsupported geography level: {level}")

    grouping = BASE_GROUPING + ["geography_id", "geography_label", "expected_country_count"]
    output = work.groupby(grouping, dropna=False, as_index=False).agg(
        selected_market_enterprise_base=("enterprise_count", "sum"),
        addressable_enterprise_base=("addressable_enterprise_count", "sum"),
        country_size_cells=("country", "count"),
        countries_with_source_data=("denominator_country", "nunique"),
        nace_country_cells_with_source_data=("nace_country_key", "nunique"),
        invalid_enterprise_input_cells=("enterprise_input_valid", invalid_cell_count),
        invalid_adoption_input_cells=("adoption_input_valid", invalid_cell_count),
        adoption_basis=("basis", "first"),
        adoption_proxy_reason=("proxy_reason", "first"),
        low_annual_value_eur=("low_annual_value_eur", "first"),
        central_annual_value_eur=("central_annual_value_eur", "first"),
        high_annual_value_eur=("high_annual_value_eur", "first"),
        public_employment_persons=("public_employment_persons", sum_or_missing),
        general_public_services_expenditure_eur=("general_public_services_expenditure_eur", sum_or_missing),
        defence_expenditure_eur=("defence_expenditure_eur", sum_or_missing),
        linked_ted_notice_count=("linked_ted_notice_count", "sum"),
    )
    output.insert(len(BASE_GROUPING), "geography_level", level)
    output["country_coverage_ratio"] = (
        output["countries_with_source_data"] / output["expected_country_count"]
    )
    output["country_coverage_status"] = "complete"
    output.loc[output["countries_with_source_data"].eq(0), "country_coverage_status"] = "no_country_data"
    output.loc[
        output["countries_with_source_data"].gt(0)
        & output["countries_with_source_data"].lt(output["expected_country_count"]),
        "country_coverage_status",
    ] = "partial"
    output["expected_nace_country_cells"] = (
        output["expected_country_count"] * output["expected_nace_code_count"]
    )
    output["nace_component_coverage_ratio"] = 0.0
    has_expected_components = output["expected_nace_country_cells"].gt(0)
    output.loc[has_expected_components, "nace_component_coverage_ratio"] = (
        output.loc[has_expected_components, "nace_country_cells_with_source_data"]
        / output.loc[has_expected_components, "expected_nace_country_cells"]
    ).clip(upper=1.0)
    output["nace_component_coverage_status"] = "complete"
    output.loc[
        output["nace_country_cells_with_source_data"].eq(0),
        "nace_component_coverage_status",
    ] = "no_component_data"
    output.loc[
        output["nace_country_cells_with_source_data"].gt(0)
        & output["nace_component_coverage_ratio"].lt(1),
        "nace_component_coverage_status",
    ] = "partial"
    return output


def calculate() -> pd.DataFrame:
    """Return business scenarios plus a separate public-procurement scenario."""
    opportunities = prepare_opportunities()
    market_inputs = prepare_enterprise_and_adoption()
    assumptions = prepare_assumptions()

    business_opportunities = opportunities[
        opportunities["denominator_method"].eq("sbs_enterprise_count")
    ].copy()
    public_opportunities = opportunities[
        opportunities["denominator_method"].eq("public_buyer_count")
    ].copy()

    # SBS business verticals retain the original adoption-based segmentation.
    joined = business_opportunities.merge(
        market_inputs,
        on=["nace_code", "technology_proxy"],
        how="left",
    )
    business_scenarios = []
    for scenario, formula in [
        ("greenfield", lambda adoption: 1 - adoption),
        ("expansion_or_managed_service", lambda adoption: adoption),
    ]:
        frame = joined.copy()
        frame["demand_scenario"] = scenario
        frame["demand_rate"] = frame["adoption_rate"].map(formula)
        frame["addressable_enterprise_count"] = frame["enterprise_count"] * frame["demand_rate"]
        frame["denominator_country"] = frame["country"].where(frame["enterprise_count"].notna())
        business_scenarios.append(frame)
    business_detail = pd.concat(business_scenarios, ignore_index=True)
    business_detail["public_employment_persons"] = pd.NA
    business_detail["general_public_services_expenditure_eur"] = pd.NA
    business_detail["defence_expenditure_eur"] = pd.NA
    business_detail["linked_ted_notice_count"] = 0

    # Public/Government uses one observed-procurement segment. Employment and
    # expenditure remain context and are not multiplied into the estimate.
    public_detail = prepare_public_buyer_inputs(public_opportunities)
    public_detail["technology_proxy"] = "public_procurement_evidence"
    public_detail["technology_mapping_status"] = "not_required_public_buyer_method"
    public_detail["demand_scenario"] = "active_public_procurement"
    public_detail["demand_rate"] = 1.0
    public_detail["addressable_enterprise_count"] = public_detail["enterprise_count"]

    detail = pd.concat([business_detail, public_detail], ignore_index=True, sort=False)
    detail = detail.merge(
        assumptions,
        on=["vertical", "use_case_id", "technology_id", "demand_scenario"],
        how="left",
        suffixes=("", "_assumption"),
    )

    output = pd.concat(
        [
            aggregate_geography(detail, "country"),
            aggregate_geography(detail, "region"),
            aggregate_geography(detail, "europe"),
        ],
        ignore_index=True,
    )
    for label in ["low", "central", "high"]:
        output[f"{label}_annual_potential_eur"] = (
            output["addressable_enterprise_base"] * output[f"{label}_annual_value_eur"]
        )
    output["market_potential_status"] = "not_estimable_missing_validated_annual_value"
    output["validation_status"] = "blocked_missing_validated_annual_value"
    output.loc[output["assumption_status"].isna(), "assumption_status"] = "missing_assumption"
    output.loc[output["assumption_status"].eq("not_approved"), "market_potential_status"] = "not_estimable_annual_value_not_approved"
    output.loc[output["assumption_status"].eq("not_approved"), "validation_status"] = "blocked_annual_value_not_approved"
    invalid_assumption = output["assumption_status"].str.startswith(("invalid_", "approved_incomplete", "approved_currency"), na=False)
    output.loc[invalid_assumption, "market_potential_status"] = "not_estimable_invalid_annual_value_assumption"
    output.loc[invalid_assumption, "validation_status"] = "failed_annual_value_assumption_validation"
    business_mapping = (
        output["vertical_mapping_status"].eq("mapped")
        & output["technology_mapping_status"].eq("mapped_proxy")
    )
    public_mapping = output["vertical_mapping_status"].eq(
        "mapped_public_buyer_denominator"
    )
    has_input_mapping = business_mapping | public_mapping
    invalid_inputs = has_input_mapping & (
        output["invalid_enterprise_input_cells"].gt(0)
        | output["invalid_adoption_input_cells"].gt(0)
    )
    output.loc[invalid_inputs, "market_potential_status"] = "not_estimable_invalid_market_input"
    output.loc[invalid_inputs, "validation_status"] = "failed_enterprise_or_adoption_validation"
    estimable = (
        has_input_mapping
        & output["assumption_status"].eq("approved_complete")
        & output["countries_with_source_data"].gt(0)
        & output["selected_market_enterprise_base"].gt(0)
        & ~invalid_inputs
    )
    output.loc[estimable, "market_potential_status"] = "estimated_proxy_based"
    output.loc[estimable & public_mapping, "market_potential_status"] = (
        "estimated_observed_public_buyer_lower_bound"
    )
    output.loc[estimable, "validation_status"] = "passed"
    vertical_gap = ~output["vertical_mapping_status"].isin(
        ["mapped", "mapped_public_buyer_denominator"]
    )
    output.loc[vertical_gap, "market_potential_status"] = "not_estimable_vertical_mapping_gap"
    output.loc[vertical_gap, "validation_status"] = "blocked_vertical_mapping_gap"
    technology_gap = (
        output["vertical_mapping_status"].eq("mapped")
        & output["technology_mapping_status"].ne("mapped_proxy")
    )
    output.loc[technology_gap, "market_potential_status"] = "not_estimable_technology_proxy_gap"
    output.loc[technology_gap, "validation_status"] = "blocked_technology_proxy_gap"
    missing_market_inputs = (
        business_mapping
        & output["countries_with_source_data"].eq(0)
    )
    output.loc[missing_market_inputs, "market_potential_status"] = "not_estimable_missing_enterprise_or_adoption_data"
    output.loc[missing_market_inputs, "validation_status"] = "blocked_missing_enterprise_or_adoption_data"
    missing_public_buyers = public_mapping & output["selected_market_enterprise_base"].le(0)
    output.loc[missing_public_buyers, "market_potential_status"] = (
        "not_estimable_no_opportunity_linked_public_buyers"
    )
    output.loc[missing_public_buyers, "validation_status"] = (
        "blocked_no_opportunity_linked_public_buyers"
    )
    # Invalid numeric inputs take precedence over an ordinary coverage gap: a
    # reviewer needs to correct the data before a later mapping can be trusted.
    output.loc[invalid_assumption, "market_potential_status"] = "not_estimable_invalid_annual_value_assumption"
    output.loc[invalid_assumption, "validation_status"] = "failed_annual_value_assumption_validation"
    output.loc[invalid_inputs, "market_potential_status"] = "not_estimable_invalid_market_input"
    output.loc[invalid_inputs, "validation_status"] = "failed_enterprise_or_adoption_validation"
    potential_columns = ["low_annual_potential_eur", "central_annual_potential_eur", "high_annual_potential_eur"]
    negative_potential = (output[potential_columns] < 0).any(axis=1)
    output.loc[negative_potential, "market_potential_status"] = "not_estimable_invalid_calculated_value"
    output.loc[negative_potential, "validation_status"] = "failed_negative_calculated_value"
    output.loc[negative_potential, potential_columns] = pd.NA
    # A non-passing row is never allowed to carry a displayable EUR result.
    output.loc[output["validation_status"].ne("passed"), potential_columns] = pd.NA
    output["market_scope"] = MARKET_SCOPE_NAME
    output["interpretation_note"] = (
        "Country-level source data is aggregated to the configured Orange Business region or Europe total. "
        "ICT adoption is an all-business proxy. Review vertical_mapping_quality, "
        "vertical_mapping_limitation, country_coverage_status and nace_component_coverage_status. "
        "For Public/Government, opportunity-linked TED buyers are an observed lower bound; "
        "NACE O employment and COFOG expenditure are context only."
    )
    return output.sort_values(["market_potential_status", "priority_score"], ascending=[True, False])


def main() -> None:
    results = calculate()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result_path = OUTPUT_DIR / "market_potential_scenarios.csv"
    summary_path = OUTPUT_DIR / "market_potential_summary.csv"
    validation_path = OUTPUT_DIR / "market_sizing_validation_report.csv"
    results.to_csv(result_path, index=False, encoding="utf-8-sig")
    summary = results.groupby(["geography_level", "market_potential_status"], as_index=False).agg(
        scenario_rows=("opportunity_id", "size"),
        distinct_opportunity_spaces=("opportunity_id", "nunique"),
    )
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    validation_columns = [
        "opportunity_id", "vertical", "use_case_id", "technology_id", "demand_scenario",
        "nace_codes", "denominator_method", "vertical_mapping_status", "vertical_mapping_quality",
        "vertical_statistical_scope", "vertical_mapping_limitation",
        "technology_proxy", "technology_mapping_status",
        "geography_level", "geography_id", "geography_label", "countries_with_source_data",
        "expected_country_count", "country_coverage_ratio", "country_coverage_status",
        "nace_country_cells_with_source_data", "expected_nace_country_cells",
        "nace_component_coverage_ratio", "nace_component_coverage_status",
        "public_employment_persons", "general_public_services_expenditure_eur",
        "defence_expenditure_eur", "linked_ted_notice_count",
        "market_potential_status", "validation_status", "assumption_status", "currency",
        "annual_value_method",
        "invalid_enterprise_input_cells", "invalid_adoption_input_cells",
        "low_annual_value_eur", "central_annual_value_eur", "high_annual_value_eur",
        "low_annual_potential_eur", "central_annual_potential_eur", "high_annual_potential_eur",
    ]
    results[validation_columns].to_csv(validation_path, index=False, encoding="utf-8-sig")
    print(f"Scenario rows: {len(results)}")
    print(f"Distinct opportunity spaces: {results['opportunity_id'].nunique()}")
    print(summary.to_string(index=False))
    print(f"Written: {result_path}")
    print(f"Written: {summary_path}")
    print(f"Written: {validation_path}")


if __name__ == "__main__":
    main()
