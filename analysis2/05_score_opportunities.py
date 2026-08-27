"""Score evidence-backed Orange Business opportunity spaces.

The script is deterministic and never changes the source database. It scores
only records with a complete, classified Vertical x Use Case x Technology
taxonomy. The resulting numbers are evidence indices, not market-size,
revenue, or win-probability predictions.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ANALYSIS_DIR = Path(__file__).resolve().parent
INPUT_PATH = ANALYSIS_DIR / "outputs" / "enrichment" / "auto_scoring_candidates.csv"
SCORING_DIR = ANALYSIS_DIR / "outputs" / "scoring"
SCORES_PATH = SCORING_DIR / "opportunity_scores.csv"
EVIDENCE_PATH = SCORING_DIR / "opportunity_evidence.csv"
WATCHLIST_PATH = SCORING_DIR / "watchlist.csv"
EXCLUSIONS_PATH = SCORING_DIR / "scoring_exclusions.csv"
SUMMARY_PATH = SCORING_DIR / "scoring_summary.csv"

GROUP_COLUMNS = ["vertical", "use_case_id", "technology_id"]

SIGNAL_POINTS = {
    "regulation": 4,
    "buying_signal": 4,
    "market_move": 3,
    "proof_signal": 3,
    "technology_maturity": 2,
    "market_trend": 2,
    "unknown": 1,
}
URGENT_SIGNALS = {"regulation", "buying_signal", "market_move"}


def load_input() -> pd.DataFrame:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            "Automatic enrichment input not found. Run "
            "04b_auto_enrich_candidates.py first: "
            f"{INPUT_PATH}"
        )

    data = pd.read_csv(INPUT_PATH, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    required = set(GROUP_COLUMNS) | {
        "article_id", "event_key", "source_name", "source_quality_prior",
        "signal_type", "auto_positive_groups", "classification_status",
        "enrichment_status", "date_quality_flag",
    }
    missing = required - set(data.columns)
    if missing:
        raise ValueError("Input is missing required columns: " + ", ".join(sorted(missing)))

    if data["article_id"].str.strip().eq("").any():
        raise ValueError("Input contains empty article_id values.")

    # Duplicate article IDs represent the same evidence and must not inflate a score.
    data = data.drop_duplicates(subset=["article_id"], keep="first").copy()
    data["source_quality_prior"] = pd.to_numeric(
        data["source_quality_prior"], errors="coerce"
    ).fillna(0.30).clip(lower=0, upper=1)
    data["signal_type"] = data["signal_type"].where(
        data["signal_type"].isin(SIGNAL_POINTS), "unknown"
    )
    data["signal_points"] = data["signal_type"].map(SIGNAL_POINTS)
    data["is_urgent_signal"] = data["signal_type"].isin(URGENT_SIGNALS)
    return data


def strict_eligibility(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate valid scoring evidence from retained, explainable exclusions."""
    complete_taxonomy = data[GROUP_COLUMNS].apply(lambda column: column.str.strip().ne("")).all(axis=1)
    eligible = (
        complete_taxonomy
        & data["classification_status"].eq("classified")
        & data["enrichment_status"].eq("ready_for_scoring")
        & data["date_quality_flag"].eq("valid_past")
    )

    exclusions = data.loc[~eligible].copy()
    exclusions["scoring_exclusion_reason"] = ""
    exclusions.loc[~complete_taxonomy, "scoring_exclusion_reason"] += "incomplete_taxonomy;"
    exclusions.loc[exclusions["classification_status"] != "classified", "scoring_exclusion_reason"] += "taxonomy_not_classified;"
    exclusions.loc[exclusions["enrichment_status"] != "ready_for_scoring", "scoring_exclusion_reason"] += "not_ready_for_scoring;"
    exclusions.loc[exclusions["date_quality_flag"] != "valid_past", "scoring_exclusion_reason"] += "date_not_valid_past;"
    exclusions["scoring_exclusion_reason"] = exclusions["scoring_exclusion_reason"].str.rstrip(";")

    return data.loc[eligible].copy(), exclusions


def capability_groups(values: pd.Series) -> set[str]:
    groups: set[str] = set()
    for value in values:
        groups.update(item.strip() for item in str(value).split(";") if item.strip())
    return groups


def score_opportunity(group: pd.DataFrame) -> dict[str, object]:
    first = group.iloc[0]
    evidence_count = len(group)
    independent_sources = group["source_name"].str.strip().replace("", "Unknown source").nunique()
    independent_events = group["event_key"].str.strip().replace("", "Unknown event").nunique()
    average_signal = group["signal_points"].mean()
    average_quality = group["source_quality_prior"].mean()
    groups = capability_groups(group["auto_positive_groups"])
    urgent_share = group["is_urgent_signal"].mean()

    # Attractiveness: external evidence only. Each capped component prevents
    # repeated coverage of a single event from dominating the ranking.
    signal_component = min(average_signal / 4, 1) * 30
    independence_component = min(independent_sources / 3, 1) * 25
    quality_component = min(average_quality, 1) * 25
    momentum_component = min(independent_events / 5, 1) * 20
    attractiveness_score = signal_component + independence_component + quality_component + momentum_component

    # Orange fit is a capability-alignment proxy, not a probability of sale.
    orange_fit_score = min(len(groups) / 4, 1) * 100

    # Confidence measures the strength of the evidence, not market potential.
    evidence_component = min(evidence_count / 5, 1) * 35
    confidence_quality_component = min(average_quality, 1) * 35
    confidence_independence_component = min(independent_sources / 3, 1) * 30
    confidence_score = evidence_component + confidence_quality_component + confidence_independence_component

    urgency_score = urgent_share * 100
    priority_score = (
        0.40 * attractiveness_score
        + 0.35 * orange_fit_score
        + 0.15 * confidence_score
        + 0.10 * urgency_score
    )

    passes_radar_gate = (
        independent_events >= 2
        and independent_sources >= 2
        and confidence_score >= 45
    )

    return {
        "opportunity_id": " | ".join(str(first[column]).strip() for column in GROUP_COLUMNS),
        "vertical": first["vertical"],
        "use_case_id": first["use_case_id"],
        "technology_id": first["technology_id"],
        "evidence_count": evidence_count,
        "independent_source_count": independent_sources,
        "independent_event_count": independent_events,
        "average_source_quality": round(average_quality, 3),
        "capability_groups": "; ".join(sorted(groups)),
        "signal_component": round(signal_component, 1),
        "independence_component": round(independence_component, 1),
        "quality_component": round(quality_component, 1),
        "momentum_component": round(momentum_component, 1),
        "attractiveness_score": round(attractiveness_score, 1),
        "orange_fit_score": round(orange_fit_score, 1),
        "confidence_score": round(confidence_score, 1),
        "urgency_score": round(urgency_score, 1),
        "priority_score": round(priority_score, 1),
        "publication_status": "RADAR" if passes_radar_gate else "WATCHLIST",
    }


def build_scores(evidence: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    evidence = evidence.copy()
    evidence["opportunity_id"] = evidence[GROUP_COLUMNS].agg(" | ".join, axis=1)
    scores = [score_opportunity(group) for _, group in evidence.groupby("opportunity_id", sort=False)]
    return pd.DataFrame(scores).sort_values(
        ["publication_status", "priority_score"], ascending=[True, False]
    ).reset_index(drop=True), evidence


def write_outputs(scores: pd.DataFrame, evidence: pd.DataFrame, exclusions: pd.DataFrame) -> None:
    SCORING_DIR.mkdir(parents=True, exist_ok=True)
    scores.to_csv(SCORES_PATH, index=False, encoding="utf-8-sig")
    evidence.to_csv(EVIDENCE_PATH, index=False, encoding="utf-8-sig")
    scores.loc[scores["publication_status"] == "WATCHLIST"].to_csv(
        WATCHLIST_PATH, index=False, encoding="utf-8-sig"
    )
    exclusions.to_csv(EXCLUSIONS_PATH, index=False, encoding="utf-8-sig")

    summary = pd.DataFrame([{
        "input_articles": len(evidence) + len(exclusions),
        "eligible_evidence_articles": len(evidence),
        "excluded_articles": len(exclusions),
        "opportunity_spaces": len(scores),
        "radar_spaces": int((scores["publication_status"] == "RADAR").sum()),
        "watchlist_spaces": int((scores["publication_status"] == "WATCHLIST").sum()),
        "median_priority_score": round(scores["priority_score"].median(), 1),
    }])
    summary.to_csv(SUMMARY_PATH, index=False, encoding="utf-8-sig")


def main() -> None:
    source = load_input()
    eligible, exclusions = strict_eligibility(source)
    if eligible.empty:
        raise ValueError("No eligible records: inspect scoring_exclusions.csv conditions.")

    scores, evidence = build_scores(eligible)
    write_outputs(scores, evidence, exclusions)

    print(f"Input records: {len(source)}")
    print(f"Eligible complete evidence: {len(evidence)}")
    print(f"Excluded records: {len(exclusions)}")
    print(f"Scored opportunity spaces: {len(scores)}")
    print(f"Radar spaces: {(scores['publication_status'] == 'RADAR').sum()}")
    print(f"Watchlist spaces: {(scores['publication_status'] == 'WATCHLIST').sum()}")
    print(f"Written: {SCORES_PATH}")
    print(f"Written: {EVIDENCE_PATH}")
    print(f"Written: {WATCHLIST_PATH}")
    print(f"Written: {EXCLUSIONS_PATH}")
    print(f"Written: {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
