from radar.intelligence import evidence_strength, normalize_signal, research_prompt_context


def test_evidence_strength_log_normalizes_volume():
    low = evidence_strength(1, 1, 1)
    high = evidence_strength(1000, 1, 1)
    assert high["volume"] <= 100
    assert high["volume"] - low["volume"] < 100
    assert evidence_strength(0, 0, 0)["score"] == 0


def test_alec_signal_names_map_to_radar_names():
    assert normalize_signal("buying") == "buying_signal"
    assert normalize_signal("proof") == "proof_signal"
    assert normalize_signal("maturity") == "technology_maturity"


def test_research_context_separates_company_guidance_from_market_evidence():
    context = research_prompt_context()
    assert "Never use them as independent proof" in context
    assert "consumer-only" in context
    assert "independence group" in context
