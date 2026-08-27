"""Load and validate the market-sizing vertical-to-NACE crosswalk."""

from __future__ import annotations

import json
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parent / "market_vertical_config.json"


def load_vertical_config(path: Path = CONFIG_PATH) -> dict:
    """Return validated configuration keyed by radar vertical."""
    if not path.exists():
        raise FileNotFoundError(f"Vertical market mapping config not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("verticals")
    if not isinstance(rows, list) or not rows:
        raise ValueError("market_vertical_config.json must contain a non-empty 'verticals' list")

    mappings: dict[str, dict] = {}
    required = {
        "vertical", "enabled", "nace_codes", "mapping_quality",
        "statistical_scope", "limitation",
    }
    for index, row in enumerate(rows, start=1):
        missing = required - set(row)
        if missing:
            raise ValueError(f"Vertical mapping row {index} is missing: {', '.join(sorted(missing))}")
        vertical = str(row["vertical"]).strip()
        if not vertical:
            raise ValueError(f"Vertical mapping row {index} has an empty vertical")
        if vertical in mappings:
            raise ValueError(f"Duplicate vertical mapping: {vertical}")

        codes = [str(code).strip() for code in row["nace_codes"] if str(code).strip()]
        if len(codes) != len(set(codes)):
            raise ValueError(f"Duplicate NACE code inside vertical mapping: {vertical}")
        if bool(row["enabled"]) and not codes:
            raise ValueError(f"Enabled vertical requires at least one NACE code: {vertical}")
        if not bool(row["enabled"]) and codes:
            raise ValueError(f"Disabled vertical must not provide NACE codes: {vertical}")

        mappings[vertical] = {
            **row,
            "vertical": vertical,
            "enabled": bool(row["enabled"]),
            "nace_codes": codes,
            "denominator_method": row.get("denominator_method", "sbs_enterprise_count"),
            "public_context_nace_code": row.get("public_context_nace_code", ""),
        }
    return {"version": payload.get("version", ""), "scope_note": payload.get("scope_note", ""), "verticals": mappings}


def target_nace_codes(path: Path = CONFIG_PATH) -> list[str]:
    """Return the sorted unique NACE codes needed by enabled mappings."""
    config = load_vertical_config(path)
    return sorted({
        code
        for mapping in config["verticals"].values()
        if mapping["enabled"]
        for code in mapping["nace_codes"]
    })
