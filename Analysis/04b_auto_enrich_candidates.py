"""Automatically enrich Innovation Radar candidates with transparent rules.

This is a first-pass triage tool, not a replacement for evidence review.  It
does not call an API or an LLM: every decision is based on the keyword matches
written into the output.  Its purpose is to remove clearly non-addressable
items and make the remaining review queue manageable.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ANALYSIS_DIR = Path(__file__).resolve().parent
ENRICHMENT_DIR = ANALYSIS_DIR / "outputs" / "enrichment"
INPUT_PATH = ENRICHMENT_DIR / "enriched_candidates.csv"
AUTO_PATH = ENRICHMENT_DIR / "auto_enriched_candidates.csv"
REVIEW_PATH = ENRICHMENT_DIR / "auto_review_queue.csv"
SCORING_INPUT_PATH = ENRICHMENT_DIR / "auto_scoring_candidates.csv"
SUMMARY_PATH = ENRICHMENT_DIR / "auto_enrichment_summary.csv"

TEXT_COLUMNS = ["title", "summary", "classification_evidence", "use_case_id", "technology_id"]

# These are capabilities Orange Business can realistically provide or integrate
# around: connectivity, cloud, cyber, data/AI, digital workplace and systems
# integration.  Keep this dictionary explicit so the team can challenge it.
ORANGE_CAPABILITY_TERMS = {
    "connectivity": ["5g", "private network", "private wireless", "connectivity", "network", "wifi", "wi-fi", "satellite", "iot", "iiot", "connected"],
    "cloud_edge": ["cloud", "edge", "data platform", "data space", "data sharing", "data sovereignty"],
    "cybersecurity": ["cyber", "security", "zero trust", "resilience", "secure by design", "security operations"],
    "data_ai": ["artificial intelligence", " ai ", "machine learning", "analytics", "predictive", "computer vision", "digital twin", "automation"],
    "industrial_operations": ["factory", "manufactur", "production", "plant", "warehouse", "supply chain", "industrial", "worker safety", "quality control", "maintenance"],
    "business_trigger": ["procurement", "tender", "deployment", "rollout", "investment", "funding", "pilot", "contract", "partnership", "regulation", "compliance"],
}

# These do not automatically mean an article is irrelevant.  They do, however,
# mean a generic mention of technology is insufficient to claim Orange fit.
NON_ADDRESSABLE_TERMS = {
    "commodity_or_incident": ["explosion", "fire outbreak", "earthquake", "fatality", "crude oil", "iron ore", "commodity price", "quarterly earnings", "share price", "dividend"],
    "biomedical_or_ecology": ["clinical trial", "patient", "cancer", "drug discovery", "gene", "biodiversity", "ecology", "wildlife", "crop yield"],
    "consumer_or_politics": ["celebrity", "football", "election campaign", "film festival", "consumer smartphone review"],
}

SIGNAL_RULES = {
    # Do not use generic words such as "act" or "standard" here. In TED data,
    # for example, "cn-standard" is a notice type rather than regulatory
    # evidence. Regulation needs an explicit legal/compliance context.
    "regulation": ["regulation", "regulatory", "directive", "legislation", "compliance requirement", "legal requirement", "policy mandate", "ai act"],
    "buying_signal": ["procurement", "tender", "request for proposal", "rfp", "contract award", "awarded", "budget"],
    "market_move": ["partnership", "acquisition", "merger", "joint venture", "launches", "rollout", "deploy", "deployment", "investment"],
    "proof_signal": ["case study", "pilot", "demonstrator", "implemented", "in operation", "successfully deployed"],
    "technology_maturity": ["commercialisation", "commercialization", "scale-up", "production-ready", "certified", "interoperable", "maturity"],
    "market_trend": ["growing demand", "market growth", "shortage", "skills gap", "increasing demand", "transition"],
}


def normalise(value: object) -> str:
    return f" {str(value or '').lower()} "


def matched_groups(text: str, rules: dict[str, list[str]]) -> list[str]:
    return [group for group, terms in rules.items() if any(term in text for term in terms)]


def matched_terms(text: str, rules: dict[str, list[str]]) -> list[str]:
    matches: list[str] = []
    for group, terms in rules.items():
        for term in terms:
            if term in text:
                matches.append(f"{group}:{term.strip()}")
    return matches


def choose_signal(text: str) -> tuple[str, list[str]]:
    for signal, terms in SIGNAL_RULES.items():
        matches = [term for term in terms if term in text]
        if matches:
            return signal, matches
    return "unknown", []


def classify(row: pd.Series) -> pd.Series:
    text = normalise(" ".join(str(row.get(column, "")) for column in TEXT_COLUMNS))
    positive_groups = matched_groups(text, ORANGE_CAPABILITY_TERMS)
    negative_groups = matched_groups(text, NON_ADDRESSABLE_TERMS)
    signal_type, signal_matches = choose_signal(text)

    status = str(row.get("classification_status", "")).strip()
    tech = str(row.get("technology_id", "")).strip()
    use_case = str(row.get("use_case_id", "")).strip()
    date_flag = str(row.get("date_quality_flag", "")).strip()
    ml_keep = str(row.get("ml_keep_recommended", "")).strip()

    positive_count = len(positive_groups)
    negative_count = len(negative_groups)
    has_complete_taxonomy = status == "classified" and bool(tech) and bool(use_case)

    if date_flag == "future_event":
        relevance, basis, review_status = "IRRELEVANT", "unsupported", "excluded"
        rationale = "Future-dated record: excluded from historical evidence and retained only through the source dataset."
    elif negative_count >= 1 and positive_count >= 1:
        relevance, basis, review_status = "REVIEW", "inferred", "pending"
        rationale = "Conflicting evidence: Orange-addressable themes and non-addressable context both matched."
    elif negative_count >= 1:
        relevance, basis, review_status = "IRRELEVANT", "unsupported", "excluded"
        rationale = "No Orange-addressable capability signal; matched non-addressable context: " + ", ".join(negative_groups)
    elif has_complete_taxonomy and positive_count >= 1:
        relevance, basis, review_status = "RELEVANT", "inferred", "auto_completed"
        rationale = "Complete taxonomy plus Orange-addressable themes: " + ", ".join(positive_groups)
    elif status == "needs_review" and positive_count >= 2 and signal_type != "unknown":
        relevance, basis, review_status = "RELEVANT", "inferred", "auto_completed"
        rationale = "Strong Orange-addressable themes despite provisional taxonomy: " + ", ".join(positive_groups) + f"; {signal_type} signal detected."
    else:
        relevance, basis, review_status = "IRRELEVANT", "unsupported", "excluded"
        rationale = "Auto-excluded: evidence is incomplete or lacks sufficient Orange-addressable capability and business-trigger signals."

    confidence_score = positive_count + (1 if has_complete_taxonomy else 0) + (1 if signal_type != "unknown" else 0) - negative_count
    confidence = "high" if confidence_score >= 4 else "medium" if confidence_score >= 2 else "low"
    enrichment_status = "ready_for_scoring" if relevance == "RELEVANT" and date_flag == "valid_past" else "excluded" if relevance == "IRRELEVANT" else "needs_review"

    return pd.Series({
        "signal_type": signal_type,
        "signal_confidence": confidence if signal_type != "unknown" else "low",
        "orange_relevance": relevance,
        "orange_relevance_confidence": confidence,
        "orange_fit_basis": basis,
        "orange_relevance_rationale": rationale,
        "enrichment_method": "transparent_rules_v2",
        "enrichment_status": enrichment_status,
        "review_status": review_status,
        "auto_positive_groups": "; ".join(positive_groups),
        "auto_negative_groups": "; ".join(negative_groups),
        "auto_matched_terms": "; ".join(matched_terms(text, ORANGE_CAPABILITY_TERMS) + matched_terms(text, NON_ADDRESSABLE_TERMS)),
        "auto_signal_terms": "; ".join(signal_matches),
    })


def run() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Run 04_enrich_candidates.py --mode enrich-rules first. Missing: {INPUT_PATH}")

    data = pd.read_csv(INPUT_PATH, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    required = {"article_id", "title", "summary", "date_quality_flag", "classification_status", "use_case_id", "technology_id"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError("Input is missing columns: " + ", ".join(sorted(missing)))

    automatic = data.apply(classify, axis=1)
    for column in automatic.columns:
        data[column] = automatic[column]

    ENRICHMENT_DIR.mkdir(parents=True, exist_ok=True)
    data.to_csv(AUTO_PATH, index=False, encoding="utf-8-sig")
    review = data[data["orange_relevance"] == "REVIEW"].copy()
    review.to_csv(REVIEW_PATH, index=False, encoding="utf-8-sig")
    scoring_input = data[data["enrichment_status"] == "ready_for_scoring"].copy()
    scoring_input.to_csv(SCORING_INPUT_PATH, index=False, encoding="utf-8-sig")

    summary = (
        data.groupby(["orange_relevance", "enrichment_status", "signal_type"], dropna=False)
        .size().reset_index(name="article_count")
        .sort_values("article_count", ascending=False)
    )
    summary.to_csv(SUMMARY_PATH, index=False, encoding="utf-8-sig")

    print(f"Input candidates: {len(data)}")
    print("Orange relevance:")
    print(data["orange_relevance"].value_counts().to_string())
    print(f"Ready for scoring: {(data['enrichment_status'] == 'ready_for_scoring').sum()}")
    print(f"Human review only: {len(review)}")
    print(f"Written: {AUTO_PATH}")
    print(f"Written: {REVIEW_PATH}")
    print(f"Written: {SCORING_INPUT_PATH}")
    print(f"Written: {SUMMARY_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automatically enrich Orange Radar candidates using transparent rules.")
    parser.parse_args()
    run()
