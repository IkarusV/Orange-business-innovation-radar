"""Load the configurable Orange Business geographic market scope."""

from __future__ import annotations

import json
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parent / "market_geography_config.json"


def load_geography() -> tuple[list[str], dict[str, str], dict[str, str], str]:
    """Return countries, country-to-region maps and the configured scope name."""
    configuration = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    countries: list[str] = []
    country_to_region: dict[str, str] = {}
    region_labels: dict[str, str] = {}
    for region in configuration["regions"]:
        region_id = region["id"]
        region_labels[region_id] = region["label"]
        for country in region["countries"]:
            if country in country_to_region:
                raise ValueError(f"Country {country} appears in more than one configured region.")
            countries.append(country)
            country_to_region[country] = region_id
    return countries, country_to_region, region_labels, configuration["scope_name"]
