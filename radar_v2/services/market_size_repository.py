from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MARKET_SIZE_EXPORT = ROOT / "imports" / "market_size" / "opportunity_market_sizes.json"


BLOCKING_LABELS = {
    "blocked_annual_value_not_approved": "Annual engagement value still requires validation",
    "blocked_no_opportunity_linked_public_buyers": "No opportunity-linked public buyers were observed",
    "blocked_technology_proxy_not_mapped": "No defensible technology-adoption proxy is mapped",
    "blocked_vertical_not_mapped": "No statistical vertical denominator is mapped",
}


def opportunity_key(vertical: str, use_case_id: str, technology_id: str) -> str:
    return f"{vertical}|{use_case_id}|{technology_id}"


def _eur(value: float | int | None) -> str:
    if value is None:
        return ""
    number = float(value)
    if number >= 1_000_000_000:
        return f"€{number / 1_000_000_000:.1f}bn"
    if number >= 1_000_000:
        return f"€{number / 1_000_000:.1f}m"
    if number >= 1_000:
        return f"€{number / 1_000:.1f}k"
    return f"€{number:,.0f}"


def _empty(reason: str = "No market-size record matches this opportunity key") -> dict[str, Any]:
    return {
        "matched": False,
        "status": "unavailable",
        "estimated": False,
        "low_eur": None,
        "central_eur": None,
        "high_eur": None,
        "range_label": "Estimate unavailable",
        "availability_label": reason,
        "scope_label": "Europe",
        "coverage_label": "No matched statistical record",
        "method_label": "Not available",
        "context_note": "",
        "blocking_reasons": [reason],
        "source_note": "Market-size pipeline export not available for this opportunity.",
    }


def _compact(record: dict[str, Any]) -> dict[str, Any]:
    market = record.get("market_size") or {}
    mapping = record.get("statistical_mapping") or {}
    low = market.get("low_eur")
    central = market.get("central_eur")
    high = market.get("high_eur")
    status = str(market.get("status") or "pending_or_unavailable")

    values = [low, central, high]
    valid_values = all(value is not None and float(value) >= 0 for value in values)
    ordered_values = valid_values and float(low) <= float(central) <= float(high)
    estimated = status == "estimated" and ordered_values
    if status == "estimated" and not ordered_values:
        status = "invalid_estimate_suppressed"

    blockers = [
        BLOCKING_LABELS.get(str(reason), str(reason).replace("_", " ").capitalize())
        for reason in market.get("blocking_reasons", [])
    ]
    coverage_ratio = market.get("coverage_ratio")
    covered = int(market.get("countries_covered") or 0)
    expected = int(market.get("countries_expected") or 0)
    if coverage_ratio is None:
        coverage_label = "Coverage not available"
    else:
        coverage_label = f"{covered} of {expected} scoped countries ({float(coverage_ratio):.0%})"

    denominator = mapping.get("denominator_method")
    method_label = {
        "sbs_enterprise_count": "Enterprise base × adoption scenario × annual engagement value",
        "public_buyer_count": "Observed opportunity-linked public buyers × annual engagement value",
    }.get(denominator, "Statistical method not available")

    public_employment = market.get("public_employment_persons")
    public_spending = market.get("general_public_services_expenditure_eur")
    if denominator == "public_buyer_count":
        parts = []
        if public_employment is not None:
            parts.append(f"{float(public_employment):,.0f} public-administration employees")
        if public_spending is not None:
            parts.append(f"{_eur(public_spending)} general-public-services expenditure")
        context_note = (
            "; ".join(parts) + ". These are context indicators, not the opportunity's market size."
            if parts else "Public-sector context is unavailable; it is never substituted for market size."
        )
    else:
        context_note = "The estimate uses the mapped enterprise population; macroeconomic context is not treated as market size."

    if estimated:
        range_label = f"{_eur(low)} – {_eur(high)}"
        availability = f"Central scenario: {_eur(central)} annual addressable potential"
    else:
        range_label = "Estimate pending"
        availability = blockers[0] if blockers else "Required inputs have not passed validation"

    return {
        "matched": True,
        "status": status,
        "estimated": estimated,
        "low_eur": float(low) if estimated else None,
        "central_eur": float(central) if estimated else None,
        "high_eur": float(high) if estimated else None,
        "range_label": range_label,
        "availability_label": availability,
        "scope_label": "Europe",
        "coverage_label": coverage_label,
        "method_label": method_label,
        "context_note": context_note,
        "blocking_reasons": blockers,
        "source_note": "Eurostat SBS/ICT inputs and validated annual-value assumptions; public opportunities use TED buyer evidence with Eurostat context.",
    }


@lru_cache(maxsize=1)
def load_index() -> dict[str, dict[str, Any]]:
    if not MARKET_SIZE_EXPORT.exists():
        return {}
    payload = json.loads(MARKET_SIZE_EXPORT.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        raise ValueError("Market-size export must be a JSON list")
    return {
        str(record["opportunity_key"]): _compact(record)
        for record in payload
        if isinstance(record, dict) and record.get("opportunity_key")
    }


def for_opportunity(vertical: str, use_case_id: str, technology_id: str) -> dict[str, Any]:
    key = opportunity_key(vertical, use_case_id, technology_id)
    return dict(load_index().get(key, _empty()))


def attach(opportunities: list[dict]) -> list[dict]:
    output = []
    for opportunity in opportunities:
        item = dict(opportunity)
        item["market_size"] = for_opportunity(
            str(item.get("vertical", "")),
            str(item.get("use_case_id", "")),
            str(item.get("technology_id", "")),
        )
        output.append(item)
    return output
