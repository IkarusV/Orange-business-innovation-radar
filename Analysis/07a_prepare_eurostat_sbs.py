"""Prepare reusable reference tables from four downloaded Eurostat SBS TSVs.

This is a read-only local-data preparation step. It does not call an LLM, does
not call an API, and never changes the original Eurostat downloads. It reads
only the requested year column from each source and writes compact CSV outputs
for later market-sizing calculations.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from market_geography import load_geography


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DIR = Path(__file__).resolve().parent / "reference" / "eurostat"

# Do not sum C and C29 because C29 is included inside Manufacturing (C).
TARGET_COUNTRIES, COUNTRY_TO_REGION, _, _ = load_geography()
TARGET_NACE_CODES = ["C", "C29"]

DATASETS = {
    "sbs_sc_ovw": {
        "path": PROJECT_ROOT / "estat_sbs_sc_ovw.tsv" / "estat_sbs_sc_ovw.tsv",
        "dimension_names": ["freq", "indic_sbs", "nace_r2", "size_emp", "geo"],
        "year": "2024",
        "indicator": "ENT_NR",
        "size_classes": ["50-249", "GE250"],
        "output": "enterprise_counts_standard.csv",
        "purpose": "primary_enterprise_denominator",
    },
    "sbs_ovw_smc": {
        "path": PROJECT_ROOT / "estat_sbs_ovw_smc.tsv" / "estat_sbs_ovw_smc.tsv",
        "dimension_names": ["freq", "size_emp", "nace_r2", "indic_sbs", "geo"],
        "year": "2024",
        "indicator": "ENT_NR",
        "size_classes": ["50-249", "250-499", "GE500"],
        "output": "enterprise_counts_extended.csv",
        "purpose": "optional_large_enterprise_detail",
    },
    "sbs_ovw_act": {
        "path": PROJECT_ROOT / "estat_sbs_ovw_act.tsv" / "estat_sbs_ovw_act.tsv",
        "dimension_names": ["freq", "nace_r2", "indic_sbs", "geo"],
        "year": "2024",
        "indicator": "ENT_NR",
        "size_classes": None,
        "output": "enterprise_counts_activity_validation.csv",
        "purpose": "vertical_nace_crosswalk_validation",
    },
    "sbs_ovw_iep": {
        "path": PROJECT_ROOT / "estat_sbs_ovw_iep.tsv" / "estat_sbs_ovw_iep.tsv",
        "dimension_names": ["freq", "nace_r2", "indic_sbs", "geo"],
        # The downloaded 2022 and 2023 values are suppressed for the selected
        # country/NACE rows. 2021 is the latest populated vintage and is
        # retained strictly as an older plausibility context, never as a
        # current-year market-size denominator.
        "year": "2021",
        "indicator": "INV_SOFT_MEUR",
        "size_classes": None,
        "output": "software_investment_context.csv",
        "purpose": "market_size_plausibility_context",
    },
}


def find_year_column(path: Path, requested_year: str) -> tuple[str, str]:
    """Find the compact dimension column and one exact year column."""
    header = pd.read_csv(path, sep="\t", dtype=str, nrows=0)
    dimension_column = header.columns[0]
    matching_years = [
        column for column in header.columns[1:]
        if str(column).strip() == requested_year
    ]

    if not matching_years:
        available = ", ".join(str(column).strip() for column in header.columns[1:])
        raise ValueError(
            f"Year {requested_year} is not available in {path.name}. "
            f"Available years: {available}"
        )

    return dimension_column, matching_years[0]


def read_and_normalise_dataset(name: str, specification: dict) -> pd.DataFrame:
    """Read one dataset, split Eurostat dimensions and retain one year."""
    path = specification["path"]
    if not path.exists():
        raise FileNotFoundError(f"Eurostat file not found for {name}: {path}")

    dimension_column, year_column = find_year_column(path, specification["year"])
    raw = pd.read_csv(
        path,
        sep="\t",
        dtype=str,
        usecols=[dimension_column, year_column],
    )

    dimensions = raw[dimension_column].str.split(",", expand=True)
    if dimensions.shape[1] != len(specification["dimension_names"]):
        raise ValueError(
            f"Unexpected dimension count in {name}: "
            f"expected {len(specification['dimension_names'])}, "
            f"found {dimensions.shape[1]}"
        )

    dimensions.columns = specification["dimension_names"]
    result = dimensions.copy()
    result["year"] = specification["year"]
    result["raw_value"] = raw[year_column].fillna("").str.strip()
    result["value"] = pd.to_numeric(
        result["raw_value"].str.extract(r"^([0-9.]+)")[0],
        errors="coerce",
    )
    result["status_flag"] = result["raw_value"].str.extract(
        r"^[0-9.]+\s*(.*)$"
    )[0].fillna("").str.strip()
    result["source_dataset"] = name
    result["purpose"] = specification["purpose"]
    return result


def filter_relevant_rows(data: pd.DataFrame, specification: dict) -> pd.DataFrame:
    """Keep only annual target-country/NACE rows for the requested measure."""
    result = data[
        (data["freq"] == "A")
        & (data["indic_sbs"] == specification["indicator"])
        & (data["geo"].isin(TARGET_COUNTRIES))
        & (data["nace_r2"].isin(TARGET_NACE_CODES))
    ].copy()
    result["region"] = result["geo"].map(COUNTRY_TO_REGION)

    if specification["size_classes"] is not None:
        result = result[result["size_emp"].isin(specification["size_classes"])].copy()

    return result


def validate_coverage(name: str, data: pd.DataFrame, specification: dict) -> dict:
    """Record coverage so missing data cannot silently look like zero demand."""
    expected = len(TARGET_COUNTRIES) * len(TARGET_NACE_CODES)
    if specification["size_classes"] is not None:
        expected *= len(specification["size_classes"])

    return {
        "source_dataset": name,
        "year": specification["year"],
        "indicator": specification["indicator"],
        "purpose": specification["purpose"],
        "expected_rows": expected,
        "rows_found": len(data),
        "numeric_values": int(data["value"].notna().sum()),
        "missing_or_suppressed": int(data["value"].isna().sum()),
        "countries_present": "; ".join(sorted(data["geo"].unique())),
    }


def write_reference_table(data: pd.DataFrame, output_name: str) -> Path:
    """Write a compact, standardised output without changing raw downloads."""
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REFERENCE_DIR / output_name

    result = data.rename(columns={
        "geo": "country",
        "nace_r2": "nace_code",
        "size_emp": "size_class",
        "value": "observed_value",
    }).copy()

    columns = [
        "source_dataset", "purpose", "year", "country", "nace_code",
        "region", "indic_sbs", "observed_value", "status_flag", "raw_value",
    ]
    if "size_class" in result.columns:
        columns.insert(6, "size_class")

    result[columns].sort_values(
        ["country", "nace_code"] + (["size_class"] if "size_class" in result.columns else [])
    ).to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def main() -> None:
    manifest_rows = []

    for name, specification in DATASETS.items():
        normalised = read_and_normalise_dataset(name, specification)
        filtered = filter_relevant_rows(normalised, specification)
        output_path = write_reference_table(filtered, specification["output"])
        manifest_rows.append(validate_coverage(name, filtered, specification))
        print(
            f"{name}: {len(filtered)} relevant rows written to {output_path}"
        )

    manifest = pd.DataFrame(manifest_rows)
    manifest_path = REFERENCE_DIR / "preparation_manifest.csv"
    manifest.to_csv(manifest_path, index=False, encoding="utf-8-sig")
    print(f"Written: {manifest_path}")
    print("Use enterprise_counts_standard.csv as the primary denominator.")
    print("Do not sum NACE C and C29; C29 is a subset of C.")


if __name__ == "__main__":
    main()
