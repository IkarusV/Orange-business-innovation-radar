from collections import Counter


def unique_domains(opportunity):
    """
    Maps opportunity technologies/use cases to broad Orange domains.
    This is a first prototype mapping, not a final Orange taxonomy.
    """
    text = (
        f"{opportunity['use_case']} "
        f"{opportunity['technology']}"
    ).lower()

    domains = set()

    if any(x in text for x in [
        "cyber", "security", "zero trust", "threat"
    ]):
        domains.add("Cybersecurity")

    if any(x in text for x in [
        "cloud", "data", "artificial intelligence",
        "machine learning", "generative ai"
    ]):
        domains.add("Cloud")

    if any(x in text for x in [
        "network", "5g", "sd-wan", "connectivity"
    ]):
        domains.add("Connectivity Solutions")

    if any(x in text for x in [
        "customer", "cx", "fraud"
    ]):
        domains.add("Customer Experience")

    if any(x in text for x in [
        "employee", "workplace"
    ]):
        domains.add("Employee Experience")

    if any(x in text for x in [
        "iot", "edge", "robotics", "computer vision",
        "industrial", "maintenance", "energy", "production"
    ]):
        domains.add("Smart Industries")

    if not domains:
        domains.add("Cloud")

    return list(domains)


def calculate_attractiveness(results):
    """
    Transparent prototype scoring.

    This is NOT an Orange-certified business model.
    It is an explainable MVP score.
    """
    if not results:
        return 0

    total = len(results)

    market = sum(
        1 for r in results
        if r["signal_type"] == "market_move"
    )

    proof = sum(
        1 for r in results
        if r["signal_type"] == "proof_signal"
    )

    regulation = sum(
        1 for r in results
        if r["signal_type"] == "regulation"
    )

    maturity = sum(
        1 for r in results
        if r["signal_type"] == "technology_maturity"
    )

    unique_urls = len({
        r.get("url")
        for r in results
        if r.get("url")
    })

    diversity = min(unique_urls / 10, 1)

    market_strength = min(market / 5, 1)
    evidence_quality = min((proof + regulation) / 8, 1)
    maturity_score = min(maturity / 5, 1)

    score = (
        30 * market_strength
        + 20 * diversity
        + 25 * evidence_quality
        + 15 * maturity_score
        + 10 * min(total / 20, 1)
    )

    return round(score)


def calculate_urgency(results):
    """
    Regulation + buying signal + recent evidence increase urgency.
    """
    if not results:
        return 0

    recent = sum(
        1 for r in results
        if r.get("period") == "recent"
    )

    regulation = sum(
        1 for r in results
        if r["signal_type"] == "regulation"
    )

    buying = sum(
        1 for r in results
        if r["signal_type"] == "buying_signal"
    )

    score = (
        min(recent / 15, 1) * 40
        + min(regulation / 3, 1) * 30
        + min(buying / 3, 1) * 30
    )

    return round(score)


def calculate_momentum(results):
    historical = sum(
        1 for r in results
        if r.get("period") == "historical"
    )

    recent = sum(
        1 for r in results
        if r.get("period") == "recent"
    )

    if historical == 0:
        return min(recent * 8, 100)

    ratio = recent / historical
    return round(min(ratio / 2, 1) * 100)


def calculate_diversity_penalty(domain_counts, opportunity):
    domains = unique_domains(opportunity)

    if not domains:
        return 1.0

    max_count = max(domain_counts.values(), default=0)

    if max_count <= 2:
        return 1.0

    if any(domain_counts.get(d, 0) == max_count for d in domains):
        return 0.75

    return 1.0


def build_score(opportunity, results, domain_counts):
    attractiveness = calculate_attractiveness(results)
    urgency = calculate_urgency(results)
    momentum = calculate_momentum(results)

    penalty = calculate_diversity_penalty(
        domain_counts,
        opportunity
    )

    radar_score = round(
        (
            attractiveness * 0.45
            + urgency * 0.30
            + momentum * 0.25
        ) * penalty
    )

    return {
        "attractiveness": attractiveness,
        "urgency": urgency,
        "momentum": momentum,
        "diversity_factor": penalty,
        "radar_score": radar_score,
    }


def classify_horizon(score):
    if score >= 75:
        return "NOW"
    if score >= 55:
        return "NEXT"
    if score >= 35:
        return "LATER"
    return "WATCHLIST"


def generate_why_hot(results):
    """
    Simple explainable summary for MVP.
    A future LLM can turn this into polished prose.
    """
    signals = Counter(
        r["signal_type"]
        for r in results
    )

    reasons = []

    if signals["market_move"]:
        reasons.append(
            f"{signals['market_move']} market/investment signals"
        )

    if signals["regulation"]:
        reasons.append(
            f"{signals['regulation']} regulatory signals"
        )

    if signals["proof_signal"]:
        reasons.append(
            f"{signals['proof_signal']} proof/deployment signals"
        )

    if signals["technology_maturity"]:
        reasons.append(
            f"{signals['technology_maturity']} technology maturity signals"
        )

    if not reasons:
        reasons.append("limited external evidence")

    return "; ".join(reasons)


def recommended_action(score):
    if score >= 75:
        return "Prepare a customer talking point and search for Orange references."
    if score >= 55:
        return "Run a deeper innovation study and identify potential partners."
    if score >= 35:
        return "Keep under watch and refresh external signals."
    return "Do not promote to the main radar yet."
