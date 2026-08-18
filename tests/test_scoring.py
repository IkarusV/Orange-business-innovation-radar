from radar.scoring import confidence_score, horizon_from_signal, horizon_rationale, publication_checks, score_opportunity, weighted_score


def test_weighted_score_is_deterministic_and_bounded():
    weights = {"a": 0.3, "b": 0.7}
    assert weighted_score({"a": 10, "b": 5}, weights) == 65.0
    assert weighted_score({"a": 99, "b": -4}, weights) == 30.0


def test_watchlist_requires_evidence_diversity():
    factors = {"market_signal": 8, "source_diversity": 8, "evidence_quality": 8, "momentum": 8, "strategic_relevance": 8}
    right_to_win = {"offering_fit": 8, "customer_overlap": 8, "references": 8, "partner_readiness": 8}
    assert score_opportunity(factors, right_to_win, 1, 1).status == "Watchlist"
    assert score_opportunity(factors, right_to_win, 2, 2).status == "Radar"


def test_confidence_and_horizon():
    assert confidence_score(10, 10, 10, True) == 100
    assert horizon_from_signal("regulation", 9) == "Now"
    assert horizon_from_signal("market_trend", 9) == "Next"
    assert horizon_from_signal("proof_signal", 3) == "Later"
    assert "strict Now rule" in horizon_rationale("market_trend", 9)


def test_publication_checks_explain_each_gate():
    checks = publication_checks(2, 1, 60)
    assert list(checks.values()) == [True, False, True]
