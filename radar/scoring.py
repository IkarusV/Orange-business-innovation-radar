from __future__ import annotations

from dataclasses import dataclass

from radar.config import load_json


@dataclass(frozen=True)
class ScoreResult:
    attractiveness: float
    right_to_win: float
    confidence: int
    status: str
    rationale: str


def weighted_score(factors: dict[str, float], weights: dict[str, float]) -> float:
    return round(sum(max(0, min(10, float(factors.get(key, 0)))) * weight for key, weight in weights.items()) * 10, 1)


def confidence_score(evidence_count: int, domain_count: int, quality: float, reviewed: bool = False) -> int:
    score = min(evidence_count, 4) * 10 + min(domain_count, 3) * 12 + round(max(0, min(10, quality)) * 2)
    if reviewed:
        score += 4
    return min(score, 100)


def score_opportunity(attractiveness_factors: dict, right_to_win_factors: dict, evidence_count: int, domain_count: int, reviewed: bool = False) -> ScoreResult:
    config = load_json("config/scoring.json")
    attractiveness = weighted_score(attractiveness_factors, config["attractiveness"])
    right_to_win = weighted_score(right_to_win_factors, config["right_to_win"])
    confidence = confidence_score(evidence_count, domain_count, attractiveness_factors.get("evidence_quality", 0), reviewed)
    thresholds = config["publish_thresholds"]
    publishable = evidence_count >= thresholds["minimum_evidence"] and domain_count >= thresholds["minimum_domains"] and confidence >= thresholds["minimum_confidence"]
    status = "Radar" if publishable else "Watchlist"
    rationale = (
        f"{status}: {evidence_count} evidence item(s), {domain_count} independent domain(s), "
        f"confidence {confidence}/100. Scores use deterministic weights from scoring version {config['version']}."
    )
    return ScoreResult(attractiveness, right_to_win, confidence, status, rationale)


def horizon_from_signal(signal_type: str, urgency: int) -> str:
    if urgency >= 8 and signal_type in {"regulation", "buying_signal", "proof_signal"}:
        return "Now"
    if urgency >= 5:
        return "Next"
    return "Later"


def horizon_rationale(signal_type: str, urgency: int) -> str:
    horizon = horizon_from_signal(signal_type, urgency)
    if horizon == "Now":
        return (
            f"Now because urgency is {urgency}/10 and the signal is {signal_type}, "
            "one of regulation, buying signal, or proof signal."
        )
    if horizon == "Next":
        return f"Next because urgency is {urgency}/10, but the strict Now rule is not satisfied."
    return f"Later because urgency is {urgency}/10, below the Next threshold of 5/10."


def publication_checks(evidence_count: int, domain_count: int, confidence: int) -> dict[str, bool]:
    thresholds = load_json("config/scoring.json")["publish_thresholds"]
    return {
        f"At least {thresholds['minimum_evidence']} evidence items": evidence_count >= thresholds["minimum_evidence"],
        f"At least {thresholds['minimum_domains']} independent source domains": domain_count >= thresholds["minimum_domains"],
        f"Confidence at least {thresholds['minimum_confidence']}/100": confidence >= thresholds["minimum_confidence"],
    }
