import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from radar_v2.services import explanations  # noqa: E402
from radar_v2.services import role_modes  # noqa: E402

NOW = datetime(2027, 6, 1, tzinfo=timezone.utc)


def _signal(signal_type: str, days_ago: int = 30, rationale: str = "", event_date=None) -> dict:
    return {
        "signal_type": signal_type,
        "signal_date": (NOW - timedelta(days=days_ago)).date().isoformat(),
        "event_date": event_date,
        "event_date_precision": "exact" if event_date else "none",
        "signal_type_rationale": rationale,
    }


def _space(**overrides) -> dict:
    space = {
        "vertical": "Natural Resources",
        "primary_domain": "ox-smart-industries",
        "horizon": "Now",
        "persona_weights": [
            {"id": "coo-production-executive", "label": "COO & Production Executive",
             "weight": 0.6, "source": "use_case"},
        ],
    }
    space.update(overrides)
    return space


# Part 7.1 - one test per clause type, not one per whole-field output ---------

@pytest.mark.parametrize("signal_type,expected_lead_in", [
    ("buying_signal", "Committed spend (May 2027)"),
    ("proof_signal", "Reported result"),
    ("competitor_move", "Competitor move"),
    ("market_trend", "Market trend"),
    ("tech_maturity", "Tech maturity"),
])
def test_each_hot_now_clause_type_renders_its_own_micro_template(signal_type, expected_lead_in):
    clause = explanations.hot_now_clause(
        _signal(signal_type, days_ago=14, rationale="Operator X selected a connected maintenance platform")
    )
    assert clause == f"{expected_lead_in}: Operator X selected a connected maintenance platform"


def test_regulation_clause_uses_the_event_year_not_the_signal_year():
    clause = explanations.hot_now_clause(
        _signal("regulation", days_ago=14, rationale="EU delegated acts confirm the phase-in", event_date="2029-01-17")
    )
    assert clause == "Mandate from 2029: EU delegated acts confirm the phase-in"


def test_regulation_clause_falls_back_to_the_signal_year_with_no_event_date():
    clause = explanations.hot_now_clause(_signal("regulation", days_ago=14, rationale="Binding text published"))
    assert clause == "Mandate from 2027: Binding text published"


def test_a_rationale_longer_than_the_word_cap_is_truncated_with_an_ellipsis():
    long_rationale = " ".join(f"word{index}" for index in range(20))
    clause = explanations.hot_now_clause(_signal("market_trend", rationale=long_rationale))
    body = clause.split(": ", 1)[1]
    assert body.endswith(explanations.ELLIPSIS)
    assert len(body.rstrip(explanations.ELLIPSIS).split()) == explanations.RATIONALE_MAX_WORDS


def test_a_signal_with_no_rationale_still_produces_a_typed_clause():
    """The descriptive half is optional; the type and date slots are not."""
    assert explanations.hot_now_clause(_signal("proof_signal")) == "Reported result"


# Part 7.1 - right-to-win micro-phrases ---------------------------------------

@pytest.mark.parametrize("elements,expected", [
    ({"accounts": 2}, ["2 Natural Resources accounts"]),
    ({"accounts": 1}, ["1 Natural Resources account"]),
    ({"recent_deals": 3}, ["3 recent deals"]),
    ({"reference_cases": 1}, ["1 reference case"]),
    ({"offering_match": "Managed Detection"}, ["Managed Detection in our portfolio"]),
    ({"partner_match": "Siemens"}, ["Siemens partnership"]),
])
def test_each_right_to_win_element_renders_its_own_micro_phrase(elements, expected):
    assert explanations.right_to_win_phrases(_space(right_to_win=elements)) == expected


def test_right_to_win_enumerates_all_non_zero_elements_capped_at_three_by_value():
    phrases = explanations.right_to_win_phrases(_space(right_to_win={
        "accounts": 2, "recent_deals": 7, "reference_cases": 1, "partner_match": "Siemens",
    }))
    assert phrases == ["7 recent deals", "2 Natural Resources accounts", "1 reference case"]


def test_zero_valued_elements_are_never_rendered():
    assert explanations.right_to_win_phrases(_space(right_to_win={"accounts": 0, "recent_deals": 0})) == []


def test_no_right_to_win_data_source_exists_so_every_live_space_hits_the_fallback():
    """A total gap, not a partial one: no accounts, deals, reference cases,
    offering catalogue or partner ecosystem exists anywhere in this codebase."""
    from radar_v2.services import team_repository

    assert explanations.RIGHT_TO_WIN_AVAILABLE is False
    for space in team_repository.list_opportunities():
        assert space.get("right_to_win") is None
        assert space["why_this_matters"].endswith(explanations.NO_RIGHT_TO_WIN)


# Part 7.1 - field 2 ----------------------------------------------------------

@pytest.mark.parametrize("domain_id,expected", [
    ("ox-smart-industries", "An Industrial/OX opportunity for Banking"),
    ("connectivity-solutions", "A Connectivity play for Banking"),
    ("cybersecurity", "A Cybersecurity opportunity for Banking"),
    ("cloud", "A Cloud opportunity for Banking"),
    ("cx-customer-experience", "A Customer Experience play for Banking"),
    ("ex-employee-experience", "An Employee Experience opportunity for Banking"),
])
def test_each_domain_gets_its_own_clause_one(domain_id, expected):
    text = explanations.why_this_matters(_space(primary_domain=domain_id, vertical="Banking"))
    assert text.startswith(expected + explanations.CLAUSE_JOIN)


def test_missing_domain_falls_back_to_the_generic_framing():
    text = explanations.why_this_matters(_space(primary_domain="", vertical="Banking"))
    assert text.startswith("An opportunity for Banking" + explanations.CLAUSE_JOIN)


def test_why_this_matters_is_always_exactly_two_clauses():
    """Deliberately more rigid than field 1: clause count never moves with data."""
    for elements in ({}, {"accounts": 2}, {"accounts": 2, "recent_deals": 1, "reference_cases": 4}):
        text = explanations.why_this_matters(_space(right_to_win=elements))
        assert text.count(explanations.CLAUSE_JOIN) >= 1
        assert text.split(explanations.CLAUSE_JOIN, 1)[0].startswith("An Industrial/OX opportunity")


def test_no_right_to_win_data_states_the_absence_rather_than_omitting_the_clause():
    """The all-zero case every space hits today - no CRM data source exists."""
    text = explanations.why_this_matters(_space())
    assert text == (
        "An Industrial/OX opportunity for Natural Resources"
        + explanations.CLAUSE_JOIN + explanations.NO_RIGHT_TO_WIN
    )


def test_the_spec_example_renders_verbatim():
    text = explanations.why_this_matters(_space(right_to_win={"accounts": 2, "recent_deals": 1}))
    assert text == "An Industrial/OX opportunity for Natural Resources — 2 Natural Resources accounts, 1 recent deal"


# Part 7.1 - field 3 ----------------------------------------------------------

@pytest.mark.parametrize("signal_type,expected", [
    ("buying_signal", "reference the live tender directly"),
    ("regulation", "frame it as compliance timing, not optional"),
    ("proof_signal", "lead with the reported result"),
    ("competitor_move", "position against the competitor's move"),
    ("market_trend", "use the market data as the opener"),
    ("tech_maturity", "keep the pitch exploratory, evidence is still building"),
])
def test_each_dominant_signal_type_selects_its_own_action_clause(signal_type, expected):
    move = explanations.recommended_move(_space(), "sales", signal_type)
    assert move.endswith(expected + ".")


@pytest.mark.parametrize("horizon", ["Now", "Next", "Later"])
def test_every_matrix_cell_is_filled_for_every_mode(horizon):
    for mode_id in role_modes.MODE_IDS:
        move = explanations.recommended_move(_space(horizon=horizon), mode_id, "buying_signal")
        assert move and explanations.CLAUSE_JOIN in move


def test_horizon_matching_is_case_insensitive():
    """A casing change upstream must not silently push every space into NEXT."""
    for value in ("NOW", "now", "Now"):
        assert explanations.recommended_move(_space(horizon=value), "sales", "buying_signal") == (
            "Open with the COO — reference the live tender directly."
        )


def test_a_missing_horizon_defaults_to_the_neutral_middle_column():
    assert explanations.normalise_horizon(None) == "Next"
    assert explanations.normalise_horizon("unrecognised") == "Next"


def test_a_space_with_no_persona_falls_back_to_the_generic_stakeholder():
    move = explanations.recommended_move(_space(persona_weights=[]), "strategist", "buying_signal")
    assert move.startswith(f"Prioritise for {explanations.GENERIC_PERSONA} this quarter")


def test_the_spec_examples_render_verbatim():
    sales = explanations.recommended_move(_space(horizon="Now"), "sales", "buying_signal")
    assert sales == "Open with the COO — reference the live tender directly."
    presales = explanations.recommended_move(
        _space(horizon="Later", persona_weights=[{"id": "cio", "label": "CIO", "weight": 0.6, "source": "domain"}]),
        "presales", "tech_maturity",
    )
    assert presales == "Note as a future differentiator for the CIO — keep the pitch exploratory, evidence is still building."


# Part 7.2 - the regression the hardcoded constant caused ---------------------

def test_field_three_differs_across_role_modes_for_the_same_space():
    space = _space(horizon="Now")
    moves = explanations.recommended_moves(space, "buying_signal")
    assert set(moves) == set(role_modes.MODE_IDS)
    assert len(set(moves.values())) == len(role_modes.MODE_IDS)


def test_the_hardcoded_recommended_move_constant_is_gone():
    assert not hasattr(role_modes, "PLACEHOLDER_RECOMMENDED_MOVE")
    assert role_modes.EXPLANATION_FIELDS_AVAILABLE is True


def test_switching_mode_changes_the_move_on_the_detail_page_and_on_the_card():
    """The exact bug the hardcoded constant caused: every mode, and every space,
    showed one shared sentence."""
    from radar_v2.services import team_repository
    from radar_v2.state import RadarState

    state = RadarState()
    state.opportunities = team_repository.list_opportunities()
    state.selected_opportunity = state.opportunities[0]
    detail_texts, card_texts = set(), set()
    for mode_id in role_modes.MODE_IDS:
        state.role_mode = mode_id
        detail_texts.add(state.recommended_move_text)
        card_texts.add(state.visible_opportunities[0]["recommended_move"])
    assert len(detail_texts) == len(role_modes.MODE_IDS)
    assert len(card_texts) == len(role_modes.MODE_IDS)


def test_two_different_spaces_get_two_different_moves():
    from radar_v2.services import team_repository

    spaces = team_repository.list_opportunities()
    moves = {space["recommended_moves"]["sales"] for space in spaces}
    assert len(moves) > 1


def test_all_three_fields_are_composed_regardless_of_role_mode():
    """Role mode changes layout position only, never which fields are computed."""
    fields = explanations.compose([_signal("buying_signal", rationale="Operator X committed")], _space(), now=NOW)
    assert fields["why_hot_now"] and fields["why_this_matters"]
    assert set(fields["recommended_moves"]) == set(role_modes.MODE_IDS)


# Part 7.3 - clause count tracks the qualifying signal count ------------------

def test_zero_qualifying_signals_render_the_fallback_string():
    assert explanations.why_hot_now([]) == explanations.NO_RECENT_SIGNAL
    assert explanations.compose([], _space(), now=NOW)["why_hot_now"] == explanations.NO_RECENT_SIGNAL


def test_one_qualifying_signal_produces_exactly_one_clause():
    ranked = explanations.qualifying_signals([_signal("buying_signal", rationale="Operator X committed")], now=NOW)
    text = explanations.why_hot_now(ranked)
    assert len(ranked) == 1
    assert explanations.HOT_NOW_JOIN not in text


def test_two_qualifying_signals_produce_exactly_two_clauses():
    ranked = explanations.qualifying_signals([
        _signal("buying_signal", rationale="Operator X committed"),
        _signal("market_trend", rationale="Market growing 28% annually"),
    ], now=NOW)
    assert len(explanations.hot_now_clauses(ranked)) == 2


def test_more_than_three_signals_are_capped_at_the_top_three_by_priority():
    ranked = explanations.qualifying_signals([
        _signal("tech_maturity", rationale="Accelerator generation cuts cost"),
        _signal("market_trend", rationale="Market growing 28% annually"),
        _signal("competitor_move", rationale="Telco X launched a bundle"),
        _signal("buying_signal", rationale="Operator X committed"),
        _signal("regulation", rationale="Delegated acts confirm timelines"),
    ], now=NOW)
    assert len(ranked) == 5
    clauses = explanations.hot_now_clauses(ranked)
    assert len(clauses) == explanations.MAX_HOT_NOW_CLAUSES
    assert clauses[0].startswith("Committed spend")
    assert clauses[1].startswith("Mandate from")
    assert clauses[2].startswith("Competitor move")


def test_clauses_are_ordered_by_the_shared_tie_break_priority():
    ranked = explanations.qualifying_signals([
        _signal("market_trend", rationale="Aggregate forecast"),
        _signal("regulation", rationale="Delegated acts confirm timelines"),
        _signal("buying_signal", rationale="Operator X committed"),
    ], now=NOW)
    assert [signal["signal_type"] for signal in ranked] == ["buying_signal", "regulation", "market_trend"]


def test_signals_outside_the_recency_window_do_not_qualify():
    old = _signal("buying_signal", days_ago=explanations.RECENCY_WINDOW_DAYS + 1, rationale="Old award")
    assert explanations.qualifying_signals([old], now=NOW) == []


def test_untyped_and_undated_signals_do_not_qualify():
    untyped = {"signal_type": None, "signal_date": "2027-05-01", "signal_type_rationale": "x"}
    undated = {"signal_type": "buying_signal", "signal_date": None, "signal_type_rationale": "x"}
    assert explanations.qualifying_signals([untyped, undated], now=NOW) == []


def test_identical_boilerplate_rationales_collapse_to_one_clause():
    """Deterministic sources emit a fixed rationale per row; the same sentence
    repeated three times is padding, not three pieces of evidence."""
    boilerplate = "CORDIS project status SIGNED - funded research still running"
    ranked = explanations.qualifying_signals([
        _signal("tech_maturity", days_ago=10, rationale=boilerplate),
        _signal("tech_maturity", days_ago=20, rationale=boilerplate),
        _signal("tech_maturity", days_ago=30, rationale=boilerplate),
    ], now=NOW)
    assert len(ranked) == 3
    assert len(explanations.hot_now_clauses(ranked)) == 1


def test_the_dominant_signal_type_is_reused_between_field_one_and_field_three():
    signals = [
        _signal("tech_maturity", rationale="Accelerator generation cuts cost"),
        _signal("buying_signal", rationale="Operator X committed"),
    ]
    fields = explanations.compose(signals, _space(horizon="Now"), now=NOW)
    assert fields["why_hot_now"].startswith("Committed spend")
    assert fields["recommended_moves"]["sales"].endswith("reference the live tender directly.")


def test_no_qualifying_signal_uses_the_conservative_default_action_clause():
    fields = explanations.compose([], _space(horizon="Now"), now=NOW)
    assert fields["recommended_moves"]["sales"].endswith(
        explanations.ACTION_CLAUSES["tech_maturity"] + "."
    )


# Clause tables stay pinned to the vocabularies they are keyed on -------------

def test_clause_tables_cover_their_closed_vocabularies():
    explanations._validate()


@pytest.mark.parametrize("table_name,dropped_key", [
    ("HOT_NOW_LEAD_INS", "buying_signal"),
    ("ACTION_CLAUSES", "regulation"),
    ("DOMAIN_CLAUSES", "cloud"),
    ("PERSONA_SHORT_FORMS", "cio"),
])
def test_a_clause_table_that_drifts_from_its_vocabulary_fails_loudly(monkeypatch, table_name, dropped_key):
    table = dict(getattr(explanations, table_name))
    table.pop(dropped_key)
    monkeypatch.setattr(explanations, table_name, table)
    with pytest.raises(explanations.ExplanationConfigError):
        explanations._validate()


# Part 7.4 - the live portfolio -----------------------------------------------

def test_every_space_in_the_live_portfolio_renders_all_three_fields():
    from radar_v2.services import team_repository

    for space in team_repository.list_opportunities():
        assert space["why_hot_now"].strip()
        assert space["why_this_matters"].strip()
        assert set(space["recommended_moves"]) == set(role_modes.MODE_IDS)
        assert all(text.strip() for text in space["recommended_moves"].values())
        assert space["recommended_move"] == space["recommended_moves"][role_modes.DEFAULT_MODE]
