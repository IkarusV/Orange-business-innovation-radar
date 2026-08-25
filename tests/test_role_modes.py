import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from radar_v2.services import explanations, role_modes  # noqa: E402
from radar_v2.state import RadarState  # noqa: E402


def _space(space_id: int, vertical: str, domain_ids: list, relevance: int, articles: int = 1) -> dict:
    space = {
        "id": space_id, "vertical": vertical, "horizon": "Now", "domains": domain_ids,
        "primary_domain": domain_ids[0] if domain_ids else "",
        "use_case": f"Use case {space_id}", "technology": "", "summary": "",
        "relevance": relevance, "article_count": articles,
    }
    # Composed through the live path so the mode-switched card renders the same
    # per-space, per-mode move the app does, rather than a fixture string.
    space.update(explanations.compose([], space))
    return space


def _portfolio() -> list:
    return [
        _space(1, "Financial services", ["cloud", "cybersecurity"], 88, 12),
        _space(2, "Financial services", ["cybersecurity"], 74, 9),
        _space(3, "Financial services", ["cloud"], 61, 4),
        _space(4, "Financial services", ["cx-customer-experience"], 52, 3),
        _space(5, "Manufacturing", ["ox-smart-industries"], 80, 7),
    ]


def test_every_mode_covers_every_region_with_a_valid_emphasis():
    """Part 4.2 at configuration level: a region can never be dropped from a
    mode, and 'hidden' is not an expressible value."""
    assert role_modes.MODE_IDS == ["strategist", "sales", "presales"]
    for mode_id in role_modes.MODE_IDS:
        profile = role_modes.presentation(mode_id)
        assert set(profile) == set(role_modes.REGION_KEYS)
        assert set(profile.values()) <= set(role_modes.EMPHASIS_VALUES)


def test_config_rejects_a_mode_that_drops_a_region(monkeypatch, tmp_path):
    import json

    broken = json.loads(json.dumps(role_modes.CONFIG))
    broken["modes"][0]["presentation"].pop(role_modes.REGION_KEYS[0])
    target = tmp_path / "role_modes.json"
    target.write_text(json.dumps(broken), encoding="utf-8")
    monkeypatch.setattr(role_modes, "ROLE_MODES", target)
    with pytest.raises(role_modes.RoleModeConfigError):
        role_modes._load()


def test_config_rejects_a_hidden_emphasis(monkeypatch, tmp_path):
    import json

    broken = json.loads(json.dumps(role_modes.CONFIG))
    broken["modes"][0]["presentation"][role_modes.REGION_KEYS[0]] = "hidden"
    target = tmp_path / "role_modes.json"
    target.write_text(json.dumps(broken), encoding="utf-8")
    monkeypatch.setattr(role_modes, "ROLE_MODES", target)
    with pytest.raises(role_modes.RoleModeConfigError):
        role_modes._load()


def test_every_region_is_rendered_in_the_detail_page():
    """Part 4.2 at page level: all eight regions are in the response for every
    mode - a collapsed region closes its disclosure, it is never removed."""
    from radar_v2.pages.opportunity_detail import opportunity_detail

    rendered = str(opportunity_detail())
    for region_key in role_modes.REGION_KEYS:
        assert role_modes.region_label(region_key) in rendered, region_key
    assert "hidden" not in {
        value for mode_id in role_modes.MODE_IDS for value in role_modes.presentation(mode_id).values()
    }


def test_mode_seeds_filters_only_while_they_are_untouched():
    """Part 3: switching mode always changes sort and presentation, but never
    discards filters the user set."""
    state = RadarState()
    state.opportunities = _portfolio()
    assert state.role_mode == "strategist"

    state.vertical_filter = "Financial services"
    state.toggle_domain_filter("cloud")
    state.set_role_mode("sales")
    assert state.role_mode == "sales"
    assert state.vertical_filter == "Financial services"
    assert state.domain_filter == ["cloud"]

    state.set_role_mode("presales")
    assert state.vertical_filter == "Financial services"
    assert state.domain_filter == ["cloud"]


def test_untouched_filters_are_reseeded_on_switch():
    state = RadarState()
    state.opportunities = _portfolio()
    state.set_role_mode("sales")
    assert state.vertical_filter == "All sectors"
    assert state.domain_filter == []
    assert state.persona_filter == ""


def test_switching_back_and_forth_does_not_accumulate_filter_state():
    """Part 4.3."""
    state = RadarState()
    state.opportunities = _portfolio()
    baseline = (state.vertical_filter, state.horizon_filter, list(state.domain_filter), state.persona_filter)
    for mode_id in ("sales", "presales", "strategist", "sales", "strategist"):
        state.set_role_mode(mode_id)
    assert (state.vertical_filter, state.horizon_filter, list(state.domain_filter), state.persona_filter) == baseline

    state.toggle_domain_filter("cybersecurity")
    custom = list(state.domain_filter)
    for mode_id in ("sales", "presales", "strategist"):
        state.set_role_mode(mode_id)
    assert list(state.domain_filter) == custom


def test_unknown_mode_is_ignored():
    state = RadarState()
    state.set_role_mode("architect")
    assert state.role_mode == "strategist"


def test_sort_falls_back_with_a_visible_note_not_silently():
    """Part 2.2: a configured sort whose feature does not exist yet falls back
    to attractiveness and says so. Persona weighting has since landed, so
    sales now runs its real configured sort with no fallback note; presales
    still falls back since no fit score exists."""
    strategist = role_modes.sort_plan("strategist")
    assert strategist["key"] == "attractiveness"
    assert strategist["note"] == ""

    sales = role_modes.sort_plan("sales")
    assert sales["configured_key"] == "persona_weighted"
    assert sales["key"] == "persona_weighted"
    assert sales["note"] == ""

    presales = role_modes.sort_plan("presales")
    assert presales["configured_key"] == "fit_score"
    assert presales["key"] == "attractiveness"
    assert "fit score" in presales["note"]


def test_every_mode_sorts_by_score_descending():
    state = RadarState()
    state.opportunities = list(reversed(_portfolio()))
    for mode_id in role_modes.MODE_IDS:
        state.set_role_mode(mode_id)
        scores = [item["relevance"] for item in state.visible_opportunities]
        assert scores == sorted(scores, reverse=True), mode_id


def test_persona_threshold_never_applies_with_no_persona_selected():
    """A configured threshold only ever gates once a persona is actually
    picked - with none selected, no mode can render empty because of it."""
    assert role_modes.persona_threshold("sales") == 0.6
    assert role_modes.persona_threshold("presales") == 0.3
    assert role_modes.persona_threshold("strategist") is None
    assert role_modes.PERSONA_WEIGHTING_AVAILABLE is True

    state = RadarState()
    state.opportunities = _portfolio()
    for mode_id in role_modes.MODE_IDS:
        state.set_role_mode(mode_id)
        assert len(state.visible_opportunities) == len(_portfolio()), mode_id


def test_persona_threshold_filters_once_a_persona_is_selected():
    """Once a persona is picked, the mode's configured threshold (or the
    dimension's own default when a mode declares none) actually gates."""
    from radar_v2.services import personas

    cio_label = personas.label("cio")
    strong = _space(1, "Financial services", ["cloud"], 88)
    strong["persona_weights"] = [{"id": "cio", "label": cio_label, "weight": 1.0, "source": "use_case"}]
    weak = _space(2, "Financial services", ["cloud"], 90)
    weak["persona_weights"] = [{"id": "cio", "label": cio_label, "weight": 0.3, "source": "domain"}]
    none = _space(3, "Financial services", ["cloud"], 95)

    state = RadarState()
    state.opportunities = [strong, weak, none]
    state.set_role_mode("sales")  # persona_weight_threshold: 0.6
    state.set_persona_filter(cio_label)

    visible_ids = {item["id"] for item in state.visible_opportunities}
    assert visible_ids == {1}  # only the 1.0 weight clears sales' 0.6 threshold


def test_sales_persona_prompt_is_a_prompt_not_a_gate():
    state = RadarState()
    state.opportunities = _portfolio()
    state.set_role_mode("sales")
    assert state.persona_prompt_visible is True
    assert len(state.persona_options) == 8  # the closed persona vocabulary
    # The topic list stays reachable while no persona has been picked yet.
    assert len(state.visible_opportunities) == len(_portfolio())


def test_list_density_is_single_column_only_for_sales():
    state = RadarState()
    state.set_role_mode("sales")
    assert state.role_mode_is_single_column is True
    state.set_role_mode("presales")
    assert state.role_mode_is_single_column is False
    state.set_role_mode("strategist")
    assert state.role_mode_is_single_column is False


def test_strategist_acceptance_three_relevant_topics_for_a_vertical_and_domain():
    """Part 4.1: Strategist finds at least three relevant topics for a chosen
    vertical/domain combination, ranked by attractiveness."""
    state = RadarState()
    state.opportunities = _portfolio()
    state.set_role_mode("strategist")
    state.set_vertical_filter("Financial services")
    results = state.visible_opportunities
    assert len(results) >= 3
    assert [item["relevance"] for item in results] == sorted(
        (item["relevance"] for item in results), reverse=True
    )


def test_sales_acceptance_one_or_two_topics_with_a_hook():
    """Part 4.1: Sales narrows to a short, meeting-sized list for one
    vertical, with the recommended move readable on the card itself."""
    state = RadarState()
    state.opportunities = _portfolio()
    state.set_role_mode("sales")
    state.set_vertical_filter("Financial services")
    state.toggle_domain_filter("cybersecurity")
    results = state.visible_opportunities
    assert 1 <= len(results) <= 2
    # The card shows this space's own move for sales mode, not a shared string.
    assert results[0]["recommended_move"] == results[0]["recommended_moves"]["sales"]
    assert results[0]["recommended_move"] != results[0]["recommended_moves"]["strategist"]
    assert state.role_mode_is_single_column is True


def test_presales_acceptance_surfaces_a_differentiating_topic():
    """Part 4.1: Presales reaches a single leading topic, with the
    right-to-win and offering regions leading its detail page."""
    state = RadarState()
    state.opportunities = _portfolio()
    state.set_role_mode("presales")
    state.set_vertical_filter("Manufacturing")
    results = state.visible_opportunities
    assert len(results) >= 1
    assert results[0]["id"] == 5
    profile = state.region_emphasis
    assert profile["right_to_win"] == role_modes.LEAD
    assert profile["offering_matches"] == role_modes.LEAD
    assert profile["recommended_move"] == role_modes.LEAD
    assert profile["signals_evidence"] == role_modes.STANDARD


def test_presentation_profiles_match_the_specification():
    expected = {
        "strategist": {
            "signals_evidence": "lead", "score_breakdown": "lead", "why_hot_now": "standard",
            "why_this_matters": "standard", "recommended_move": "standard",
            "right_to_win": "standard", "offering_matches": "collapsed",
            "persona_relevance": "collapsed",
        },
        "sales": {
            "signals_evidence": "collapsed", "score_breakdown": "collapsed", "why_hot_now": "standard",
            "why_this_matters": "lead", "recommended_move": "lead",
            "right_to_win": "standard", "offering_matches": "standard",
            "persona_relevance": "lead",
        },
        "presales": {
            "signals_evidence": "standard", "score_breakdown": "standard", "why_hot_now": "standard",
            "why_this_matters": "standard", "recommended_move": "lead",
            "right_to_win": "lead", "offering_matches": "lead",
            "persona_relevance": "standard",
        },
    }
    for mode_id, profile in expected.items():
        assert role_modes.presentation(mode_id) == profile
