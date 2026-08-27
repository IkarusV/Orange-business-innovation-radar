"""Normalise free Eurostat enterprise ICT-adoption datasets for market sizing.

This script reads four downloaded official Eurostat TSV archives and writes one
small, reusable adoption-rate table. It makes no LLM or API calls. The source
datasets cover all non-financial business activities, not Manufacturing alone;
therefore every output rate is explicitly labelled as a sector proxy.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from market_geography import load_geography


ANALYSIS_DIR = Path(__file__).resolve().parent
RAW_DIR = ANALYSIS_DIR / "raw" / "eurostat"
REFERENCE_DIR = ANALYSIS_DIR / "reference" / "eurostat"

TARGET_COUNTRIES, COUNTRY_TO_REGION, _, _ = load_geography()
TARGET_SIZE_CLASSES = ["50-249", "GE250"]
ALL_BUSINESS_NACE = "C10-S951_X_K"

# Each rate is observed for Eurostat's all-business, non-financial aggregate.
# Its application to a specific vertical is consequently a declared proxy.
DATASETS = {
    "ai": {
        "path": RAW_DIR / "isoc_eb_ai.tsv.gz",
        "year": "2025",
        "indicator": "E_AI_TANY",
        "label": "Enterprise use of any AI technology",
        "proxy_reason": "All-business non-financial ICT rate used as a cross-vertical proxy; it is not a vertical-specific adoption rate.",
    },
    "cloud": {
        "path": RAW_DIR / "isoc_cicce_use.tsv.gz",
        "year": "2025",
        "indicator": "E_CC1_SI",
        "label": "Use of intermediate or sophisticated paid cloud services",
        "proxy_reason": "All-business non-financial ICT rate used as a cross-vertical proxy; it is not a vertical-specific adoption rate.",
    },
    "cybersecurity": {
        "path": RAW_DIR / "isoc_cisce_ra.tsv.gz",
        "year": "2024",
        "indicator": "E_SECMGE1",
        "label": "Use of at least one ICT security measure",
        "proxy_reason": "All-business non-financial ICT rate used as a cross-vertical proxy; it is not a vertical-specific adoption rate.",
    },
    "iot": {
        "path": RAW_DIR / "isoc_eb_iot.tsv.gz",
        "year": "2021",
        "indicator": "E_IOT1",
        "label": "Enterprise use of Internet of Things devices or systems",
        "proxy_reason": "All-business non-financial ICT rate used as a cross-vertical proxy; it is not vertical-specific and uses an older 2021 vintage.",
    },
}


def find_year_column(path: Path, requested_year: str) -> tuple[str, str]:
    """Read the header only and find a Eurostat year column with whitespace."""
    header = pd.read_csv(path, sep="\t", compression="gzip", dtype=str, nrows=0)
    dimension_column = header.columns[0]
    year_columns = [
        column for column in header.columns[1:]
        if str(column).strip() == requested_year
    ]
    if not year_columns:
        available = ", ".join(str(column).strip() for column in header.columns[1:])
        raise ValueError(
            f"Year {requested_year} missing from {path.name}. Available: {available}"
        )
    return dimension_column, year_columns[0]


def read_indicator(specification: dict) -> pd.DataFrame:
    """Read and parse one ICT indicator at one year without loading all years."""
    path = specification["path"]
    if not path.exists():
        raise FileNotFoundError(f"Missing downloaded Eurostat ICT file: {path}")

    dimension_column, year_column = find_year_column(path, specification["year"])
    raw = pd.read_csv(
        path,
        sep="\t",
        compression="gzip",
        dtype=str,
        usecols=[dimension_column, year_column],
    )
    dimensions = raw[dimension_column].str.split(",", expand=True)
    dimensions.columns = ["freq", "size_emp", "nace_r2", "indic_is", "unit", "geo"]

    result = dimensions.copy()
    result["raw_value"] = raw[year_column].fillna("").str.strip()
    result["adoption_rate_percent"] = pd.to_numeric(
        result["raw_value"].str.extract(r"^([0-9.]+)")[0], errors="coerce"
    )
    result["status_flag"] = result["raw_value"].str.extract(
        r"^[0-9.]+\s*(.*)$"
    )[0].fillna("").str.strip()
    return result


def filter_and_standardise(technology: str, specification: dict) -> pd.DataFrame:
    """Select compatible country/size rows and attach transparent proxy metadata."""
    data = read_indicator(specification)
    filtered = data[
        (data["freq"] == "A")
        & (data["size_emp"].isin(TARGET_SIZE_CLASSES))
        & (data["nace_r2"] == ALL_BUSINESS_NACE)
        & (data["indic_is"] == specification["indicator"])
        & (data["unit"] == "PC_ENT")
        & (data["geo"].isin(TARGET_COUNTRIES))
    ].copy()

    filtered["technology_proxy"] = technology
    filtered["technology_label"] = specification["label"]
    filtered["source_dataset"] = specification["path"].name.removesuffix(".tsv.gz")
    filtered["year"] = specification["year"]
    filtered["basis"] = "proxy"
    filtered["proxy_reason"] = specification["proxy_reason"]
    filtered["adoption_rate"] = filtered["adoption_rate_percent"] / 100
    filtered["region"] = filtered["geo"].map(COUNTRY_TO_REGION)

    return filtered.rename(columns={
        "geo": "country",
        "nace_r2": "source_nace_code",
        "size_emp": "size_class",
        "indic_is": "indicator",
    })


def validate_coverage(technology: str, data: pd.DataFrame) -> dict:
    """Expose coverage gaps; missing data must not become a zero adoption rate."""
    expected = len(TARGET_COUNTRIES) * len(TARGET_SIZE_CLASSES)
    return {
        "technology_proxy": technology,
        "year": data["year"].iloc[0] if not data.empty else "",
        "expected_rows": expected,
        "rows_found": len(data),
        "numeric_values": int(data["adoption_rate"].notna().sum()),
        "missing_or_suppressed": int(data["adoption_rate"].isna().sum()),
        "countries_present": "; ".join(sorted(data["country"].unique())),
    }


def main() -> None:
    prepared = []
    manifest_rows = []

    for technology, specification in DATASETS.items():
        result = filter_and_standardise(technology, specification)
        prepared.append(result)
        manifest_rows.append(validate_coverage(technology, result))

    rates = pd.concat(prepared, ignore_index=True)
    output_columns = [
        "technology_proxy", "technology_label", "source_dataset", "indicator",
        "year", "country", "region", "source_nace_code", "size_class", "unit",
        "adoption_rate_percent", "adoption_rate", "basis", "proxy_reason",
        "status_flag", "raw_value",
    ]
    rates = rates[output_columns].sort_values(
        ["technology_proxy", "country", "size_class"]
    )

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    rates_path = REFERENCE_DIR / "technology_adoption_rates.csv"
    manifest_path = REFERENCE_DIR / "ict_adoption_preparation_manifest.csv"
    rates.to_csv(rates_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(manifest_rows).to_csv(manifest_path, index=False, encoding="utf-8-sig")

    print(f"Prepared adoption-rate rows: {len(rates)}")
    print(f"Written: {rates_path}")
    print(f"Written: {manifest_path}")
    print("All rates are all-business non-financial proxies, not vertical-specific rates.")


if __name__ == "__main__":
    main()
