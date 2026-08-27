"""Prepare Public/Government market-sizing inputs from public data.

NACE O employment and COFOG expenditure are scale/context indicators. They are
not enterprise counts. The addressable-customer denominator is the number of
deduplicated TED buyers observed in evidence linked to each Public/Government
opportunity space. That count is a procurement-active lower bound, not the
total number of public authorities in Europe.
"""

from __future__ import annotations

import ast
import json
import re
import sqlite3
from pathlib import Path

import pandas as pd

from market_geography import load_geography


ANALYSIS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = ANALYSIS_DIR.parent
RAW_DIR = ANALYSIS_DIR / "raw" / "eurostat_public_sector"
OUTPUT_DIR = ANALYSIS_DIR / "reference" / "eurostat" / "public_sector"
EMPLOYMENT_PATH = RAW_DIR / "estat_nama_10_a64_e.tsv.gz"
EXPENDITURE_PATH = RAW_DIR / "estat_gov_10a_exp.tsv.gz"
DATABASE_PATH = (
    PROJECT_DIR
    / "BeCode_dataOrange-radar-research-pipeline"
    / "data"
    / "articles_analysis.db"
)
SCORING_INPUT_PATH = (
    ANALYSIS_DIR / "outputs" / "enrichment" / "auto_scoring_candidates.csv"
)

TARGET_COUNTRIES, COUNTRY_TO_REGION, _, MARKET_SCOPE_NAME = load_geography()
REFERENCE_YEAR = 2024
FALLBACK_YEARS = [2024, 2023, 2022]
TED_LOOKBACK_DAYS = 730

GEO_ALIASES = {"UK": "GB", "EL": "GR"}
ISO3_TO_ISO2 = {
    "AUT": "AT", "BEL": "BE", "BGR": "BG", "HRV": "HR", "CZE": "CZ",
    "DNK": "DK", "EST": "EE", "FIN": "FI", "FRA": "FR", "DEU": "DE",
    "HUN": "HU", "ISL": "IS", "IRL": "IE", "ISR": "IL", "ITA": "IT",
    "LVA": "LV", "LTU": "LT", "LUX": "LU", "NLD": "NL", "NOR": "NO",
    "POL": "PL", "PRT": "PT", "ROU": "RO", "SVK": "SK", "SVN": "SI",
    "ESP": "ES", "SWE": "SE", "CHE": "CH", "GBR": "GB",
}


def numeric_value(raw: pd.Series) -> pd.Series:
    """Convert Eurostat cells while retaining flags outside the numeric value."""
    return pd.to_numeric(
        raw.fillna("").astype(str).str.strip().str.extract(r"^(-?[0-9.]+)")[0],
        errors="coerce",
    )


def read_eurostat_long(
    path: Path,
    dimension_names: list[str],
    candidate_years: list[int],
) -> pd.DataFrame:
    """Read selected years from one compressed Eurostat TSV into long form."""
    if not path.exists():
        raise FileNotFoundError(f"Required Eurostat download is missing: {path}")
    header = pd.read_csv(path, sep="\t", compression="gzip", dtype=str, nrows=0)
    dimension_column = header.columns[0]
    year_columns = {
        int(str(column).strip()): column
        for column in header.columns[1:]
        if str(column).strip().isdigit()
        and int(str(column).strip()) in candidate_years
    }
    if not year_columns:
        raise ValueError(f"None of {candidate_years} is available in {path.name}")

    raw = pd.read_csv(
        path,
        sep="\t",
        compression="gzip",
        dtype=str,
        usecols=[dimension_column, *year_columns.values()],
    )
    dimensions = raw[dimension_column].str.split(",", expand=True)
    if dimensions.shape[1] != len(dimension_names):
        raise ValueError(
            f"Unexpected dimensions in {path.name}: expected {len(dimension_names)}, "
            f"found {dimensions.shape[1]}"
        )
    dimensions.columns = dimension_names
    wide = pd.concat([dimensions, raw[list(year_columns.values())]], axis=1)
    long = wide.melt(
        id_vars=dimension_names,
        value_vars=list(year_columns.values()),
        var_name="year_column",
        value_name="raw_value",
    )
    reverse_years = {column: year for year, column in year_columns.items()}
    long["year"] = long["year_column"].map(reverse_years)
    long["value"] = numeric_value(long["raw_value"])
    long["status_flag"] = long["raw_value"].fillna("").astype(str).str.extract(
        r"^-?[0-9.]+\s*(.*)$"
    )[0].fillna("").str.strip()
    long["geo"] = long["geo"].replace(GEO_ALIASES)
    return long.drop(columns="year_column")


def latest_by_group(data: pd.DataFrame, grouping: list[str]) -> pd.DataFrame:
    """Select the latest numeric observation separately for each group."""
    numeric = data[data["value"].notna()].copy()
    return (
        numeric.sort_values("year", ascending=False)
        .drop_duplicates(grouping, keep="first")
        .sort_values(grouping)
    )


def prepare_employment() -> pd.DataFrame:
    """Prepare NACE O total employment as public-sector scale context."""
    data = read_eurostat_long(
        EMPLOYMENT_PATH,
        ["freq", "unit", "nace_r2", "na_item", "geo"],
        FALLBACK_YEARS,
    )
    data = data[
        data["freq"].eq("A")
        & data["unit"].eq("THS_PER")
        & data["nace_r2"].eq("O")
        & data["na_item"].eq("EMP_DC")
        & data["geo"].isin(TARGET_COUNTRIES)
    ].copy()
    data = latest_by_group(data, ["geo"])
    data["public_employment_persons"] = data["value"] * 1_000
    return data.rename(columns={
        "geo": "country",
        "year": "employment_year",
        "status_flag": "employment_status_flag",
    })[[
        "country", "employment_year", "public_employment_persons",
        "employment_status_flag",
    ]]


def prepare_expenditure() -> pd.DataFrame:
    """Prepare GF01/GF02 expenditure as context, never as customer count."""
    data = read_eurostat_long(
        EXPENDITURE_PATH,
        ["freq", "unit", "sector", "cofog99", "na_item", "geo"],
        FALLBACK_YEARS,
    )
    data = data[
        data["freq"].eq("A")
        & data["unit"].eq("MIO_EUR")
        & data["sector"].eq("S13")
        & data["cofog99"].isin(["GF01", "GF02"])
        & data["na_item"].eq("TE")
        & data["geo"].isin(TARGET_COUNTRIES)
    ].copy()
    data = latest_by_group(data, ["geo", "cofog99"])
    data["expenditure_eur"] = data["value"] * 1_000_000
    pivot_value = data.pivot(index="geo", columns="cofog99", values="expenditure_eur")
    pivot_year = data.pivot(index="geo", columns="cofog99", values="year")
    result = pd.DataFrame(index=sorted(set(pivot_value.index) | set(pivot_year.index)))
    result["general_public_services_expenditure_eur"] = pivot_value.get("GF01")
    result["defence_expenditure_eur"] = pivot_value.get("GF02")
    result["general_public_services_year"] = pivot_year.get("GF01")
    result["defence_expenditure_year"] = pivot_year.get("GF02")
    return result.reset_index(names="country")


def coerce_list(value) -> list[str]:
    """Convert list-like TED fields to a clean list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        parsed = text
    if isinstance(parsed, (list, tuple)):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [str(parsed).strip()] if str(parsed).strip() else []


def normalise_country(value) -> str:
    """Map TED two/three-letter country values to the configured ISO2 codes."""
    values = coerce_list(value)
    if not values:
        return ""
    country = values[0].upper()
    return ISO3_TO_ISO2.get(country, GEO_ALIASES.get(country, country))


def buyer_names_from_summary(summary: str) -> list[str]:
    """Extract collector-provided buyer names from the structured TED summary."""
    match = re.search(r"Buyer:\s*(.*?)\s*\|\s*Country:", summary or "")
    return coerce_list(match.group(1)) if match else []


def normalise_buyer(name: str) -> str:
    """Create a conservative deduplication key without risky entity matching."""
    return re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()


def read_ted_buyers() -> pd.DataFrame:
    """Read and deduplicate recent TED buyer observations from SQLite."""
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(f"Research database not found: {DATABASE_PATH}")
    query = """
        SELECT id AS article_id, published_date, summary, extra
        FROM articles
        WHERE source_type = 'ted'
    """
    connection = sqlite3.connect(f"file:{DATABASE_PATH.resolve()}?mode=ro", uri=True)
    try:
        raw = pd.read_sql_query(query, connection)
    finally:
        connection.close()

    raw["published_at"] = pd.to_datetime(raw["published_date"], errors="coerce", utc=True)
    latest = raw["published_at"].max()
    cutoff = latest - pd.Timedelta(days=TED_LOOKBACK_DAYS) if pd.notna(latest) else pd.NaT
    if pd.notna(cutoff):
        raw = raw[raw["published_at"].ge(cutoff)].copy()

    records = []
    for row in raw.itertuples(index=False):
        try:
            metadata = json.loads(row.extra) if row.extra else {}
        except json.JSONDecodeError:
            metadata = {}
        country = normalise_country(metadata.get("buyer_country"))
        if country not in TARGET_COUNTRIES:
            continue
        for buyer in buyer_names_from_summary(row.summary or ""):
            buyer_key = normalise_buyer(buyer)
            if buyer_key:
                records.append({
                    "article_id": str(row.article_id),
                    "country": country,
                    "buyer_name": buyer,
                    "buyer_key": f"{country}|{buyer_key}",
                    "published_at": row.published_at,
                })
    result = pd.DataFrame(records)
    if result.empty:
        return pd.DataFrame(columns=[
            "article_id", "country", "buyer_name", "buyer_key", "published_at",
        ])
    return result.drop_duplicates(["article_id", "buyer_key"])


def prepare_opportunity_buyer_counts(buyers: pd.DataFrame) -> pd.DataFrame:
    """Count unique TED buyers linked to each Public/Government opportunity."""
    scoring = pd.read_csv(
        SCORING_INPUT_PATH,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    required = {"article_id", "vertical", "use_case_id", "technology_id"}
    missing = required - set(scoring.columns)
    if missing:
        raise ValueError("Scoring input is missing: " + ", ".join(sorted(missing)))
    scoring = scoring[
        scoring["vertical"].eq("Public/Gov sector")
        & scoring["use_case_id"].str.strip().ne("")
        & scoring["technology_id"].str.strip().ne("")
    ][list(required)].drop_duplicates()
    linked = scoring.merge(buyers, on="article_id", how="inner")
    if linked.empty:
        return pd.DataFrame(columns=[
            "vertical", "use_case_id", "technology_id", "country",
            "unique_public_buyer_count", "linked_ted_notice_count",
        ])
    return linked.groupby(
        ["vertical", "use_case_id", "technology_id", "country"],
        as_index=False,
    ).agg(
        unique_public_buyer_count=("buyer_key", "nunique"),
        linked_ted_notice_count=("article_id", "nunique"),
    )


def prepare_country_context(buyers: pd.DataFrame) -> pd.DataFrame:
    """Combine employment, expenditure and overall observed buyer coverage."""
    base = pd.DataFrame({"country": TARGET_COUNTRIES})
    base["region"] = base["country"].map(COUNTRY_TO_REGION)
    employment = prepare_employment()
    expenditure = prepare_expenditure()
    buyer_counts = (
        buyers.groupby("country", as_index=False)
        .agg(
            observed_unique_ted_buyers=("buyer_key", "nunique"),
            observed_ted_notices=("article_id", "nunique"),
        )
        if not buyers.empty
        else pd.DataFrame(columns=[
            "country", "observed_unique_ted_buyers", "observed_ted_notices",
        ])
    )
    result = base.merge(employment, on="country", how="left")
    result = result.merge(expenditure, on="country", how="left")
    result = result.merge(buyer_counts, on="country", how="left")
    result[["observed_unique_ted_buyers", "observed_ted_notices"]] = result[
        ["observed_unique_ted_buyers", "observed_ted_notices"]
    ].fillna(0).astype(int)
    result["employment_coverage_status"] = result["public_employment_persons"].notna().map(
        {True: "available", False: "missing"}
    )
    result["expenditure_coverage_status"] = (
        result[[
            "general_public_services_expenditure_eur", "defence_expenditure_eur",
        ]].notna().any(axis=1).map({True: "available", False: "missing"})
    )
    result["buyer_denominator_method"] = "deduplicated_opportunity_linked_ted_buyers"
    result["buyer_denominator_interpretation"] = (
        "Observed procurement-active lower bound; not the total number of public authorities."
    )
    result["market_scope"] = MARKET_SCOPE_NAME
    return result


def main() -> None:
    buyers = read_ted_buyers()
    country_context = prepare_country_context(buyers)
    opportunity_buyers = prepare_opportunity_buyer_counts(buyers)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    context_path = OUTPUT_DIR / "public_sector_country_context.csv"
    buyer_path = OUTPUT_DIR / "public_buyer_counts_by_opportunity.csv"
    manifest_path = OUTPUT_DIR / "public_sector_preparation_manifest.csv"
    country_context.to_csv(context_path, index=False, encoding="utf-8-sig")
    opportunity_buyers.to_csv(buyer_path, index=False, encoding="utf-8-sig")

    manifest = pd.DataFrame([
        {
            "dataset": "nama_10_a64_e",
            "role": "NACE O employment context",
            "countries_with_data": int(country_context["public_employment_persons"].notna().sum()),
            "reference_year": REFERENCE_YEAR,
        },
        {
            "dataset": "gov_10a_exp",
            "role": "GF01/GF02 expenditure context",
            "countries_with_data": int(
                country_context[[
                    "general_public_services_expenditure_eur",
                    "defence_expenditure_eur",
                ]].notna().any(axis=1).sum()
            ),
            "reference_year": REFERENCE_YEAR,
        },
        {
            "dataset": "TED articles_analysis.db",
            "role": "Opportunity-linked unique public-buyer denominator",
            "countries_with_data": int(opportunity_buyers["country"].nunique()) if not opportunity_buyers.empty else 0,
            "reference_year": f"latest observation minus {TED_LOOKBACK_DAYS} days",
        },
    ])
    manifest.to_csv(manifest_path, index=False, encoding="utf-8-sig")

    print(f"Configured countries: {len(TARGET_COUNTRIES)}")
    print(f"Countries with NACE O employment: {country_context['public_employment_persons'].notna().sum()}")
    print(
        "Countries with GF01/GF02 expenditure: "
        f"{country_context[['general_public_services_expenditure_eur', 'defence_expenditure_eur']].notna().any(axis=1).sum()}"
    )
    print(f"Recent deduplicated TED buyers: {buyers['buyer_key'].nunique() if not buyers.empty else 0}")
    print(f"Public opportunity-country buyer rows: {len(opportunity_buyers)}")
    print(f"Written: {context_path}")
    print(f"Written: {buyer_path}")
    print(f"Written: {manifest_path}")
    print("Database opened read-only. No source records were modified.")


if __name__ == "__main__":
    main()
