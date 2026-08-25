import json
from pathlib import Path
from typing import Tuple

from common.business_domains import DomainIndex, build_index
from common.geography import GeographyIndex, build_index as build_geography_index
from common.personas import PersonaIndex, build_index as build_persona_index

TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "config" / "taxonomy.json"


def load_taxonomy(path: Path = TAXONOMY_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        taxonomy = json.load(f)
    build_index(taxonomy)  # fails loudly on an unknown or missing business domain slug
    build_persona_index(taxonomy)  # same for an unknown persona slug or an off-tier weight
    build_geography_index(taxonomy)  # same for a duplicate region or a country in two regions
    return taxonomy


def taxonomy_block(taxonomy: dict) -> str:
    lines = ["USE CASES:"]
    for entry in taxonomy["use_cases"]:
        lines.append(f'{entry["id"]} — {entry["label"]}: {entry["definition"]}')
    lines.append("")
    lines.append("TECHNOLOGIES:")
    for entry in taxonomy["technologies"]:
        lines.append(f'{entry["id"]} — {entry["label"]}: {entry["definition"]}')
    return "\n".join(lines)


def valid_ids(taxonomy: dict) -> Tuple[set, set]:
    use_case_ids = {e["id"] for e in taxonomy["use_cases"]}
    technology_ids = {e["id"] for e in taxonomy["technologies"]}
    return use_case_ids, technology_ids


def domain_index(path: Path = TAXONOMY_PATH) -> DomainIndex:
    """The business-domain mapping tables as configured. Read fresh so a
    correction to taxonomy.json takes effect on the next backfill without a
    restart - the derived values must never drift from configuration."""
    return build_index(load_taxonomy(path))


def persona_index(path: Path = TAXONOMY_PATH) -> PersonaIndex:
    """The persona weight tables and the suppression list as configured, read
    fresh for the same reason as domain_index()."""
    return build_persona_index(load_taxonomy(path))


def geography_index(path: Path = TAXONOMY_PATH) -> GeographyIndex:
    """The region vocabulary and its country membership as configured, read
    fresh for the same reason as domain_index() - extending eastern-europe with
    a country a live signal named must take effect on the next backfill."""
    return build_geography_index(load_taxonomy(path))
