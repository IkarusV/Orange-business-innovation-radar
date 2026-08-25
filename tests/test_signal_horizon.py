import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1] / "Pipelineteamfile"
sys.path.insert(0, str(PIPELINE))

from common import signal_types
from common.signal_types import LATER, NEXT, NOW, aggregate_horizon, signal_horizon_prior
from radar_v2.services import horizon

NOW_TS = datetime(2026, 8, 25, tzinfo=timezone.utc)


def _signal(signal_type, days_ago=1, source="Source A", confidence=0.9, event_date=None, precision="none"):
    return {
        "signal_type": signal_type,
        "signal_type_confidence": confidence,
        "signal_date": (NOW_TS - timedelta(days=days_ago)).date().isoformat(),
        "event_date": event_date,
        "event_date_precision": precision,
        "source_name": source,
    }


# --- Part 6: independence from attractiveness / volume ---------------------


def test_horizon_reads_only_signal_type_date_source_and_confidence():
    """The rules must never see an attractiveness input. Poisoning every
    volume-derived field a space carries must not move the badge."""
    signals = [
        _signal("buying_signal", source="TED"),
        _signal("buying_signal", source="UK Find a Tender", days_ago=10),
    ]
    baseline = aggregate_horizon(signals, now=NOW_TS)

    poisoned = []
    for signal in signals:
        enriched = dict(signal)
        enriched.update({
            "relevance": 0, "article_count": 999, "confidence": 0.0,
            "raw_market": 0.0, "market_signal_strength": 0.0, "avg_client_relevance": 0.0,
            "novelty_momentum": 100.0, "client_relevance": 1.0,
        })
        poisoned.append(enriched)

    assert aggregate_horizon(poisoned, now=NOW_TS).horizon == baseline.horizon
    assert aggregate_horizon(poisoned, now=NOW_TS).rule == baseline.rule


def test_app_layer_projects_away_every_non_horizon_field():
    """radar_v2.services.horizon is the only path the app uses. It must strip
    everything that is not a declared horizon input before the rules run."""
    row = {
        "source_name": "TED", "signal_type": "buying_signal", "signal_type_confidence": 0.9,
        "signal_date": "2026-08-20", "event_date": None, "event_date_precision": "none",
        "confidence": 0.95, "article_count": 42, "relevance": 88, "extra": "{}",
        "published_date": "2026-08-20", "collected_at": "2026-08-21",
    }
    projected = horizon.signals_from_rows([row])[0]
    assert set(projected) == set(horizon.SIGNAL_FIELDS)
    assert "confidence" not in projected and "article_count" not in projected


def test_high_volume_tech_maturity_only_space_is_later():
    """Twenty recent, high-confidence signals from many sources - a space that
    would score very well on attractiveness - is still Later when every one of
    them is about a technology maturing rather than anyone buying it."""
    signals = [
        _signal("tech_maturity", days_ago=index % 60, source=f"Lab {index}")
        for index in range(20)
    ]
    verdict = aggregate_horizon(signals, now=NOW_TS)
    assert verdict.horizon == LATER
    assert verdict.rule == "later_default"
    assert verdict.later_count == 20


def test_low_volume_single_recent_tender_is_next():
    """One tender is thin evidence by any volume measure and would score near
    the bottom on attractiveness - but it is committed money, so it is Next,
    not Later."""
    verdict = aggregate_horizon([_signal("buying_signal", days_ago=3, source="TED")], now=NOW_TS)
    assert verdict.horizon == NEXT
    assert verdict.rule == "next_concrete_but_below_now_bar"
    assert verdict.now_count == 1


# --- Part 5: the aggregation rules, in order -------------------------------


def test_now_requires_two_signals_two_sources_and_something_recent():
    verdict = aggregate_horizon(
        [_signal("buying_signal", days_ago=5, source="TED"),
         _signal("proof_signal", days_ago=200, source="Healthcare Dive")],
        now=NOW_TS,
    )
    assert verdict.horizon == NOW
    assert verdict.rule == "now_converging_evidence"
    assert verdict.distinct_sources == 2


def test_two_concrete_signals_from_one_source_do_not_reach_now():
    verdict = aggregate_horizon(
        [_signal("buying_signal", days_ago=5, source="TED"),
         _signal("buying_signal", days_ago=9, source="TED")],
        now=NOW_TS,
    )
    assert verdict.horizon == NEXT
    assert verdict.distinct_sources == 1


def test_two_concrete_signals_with_nothing_recent_do_not_reach_now():
    verdict = aggregate_horizon(
        [_signal("buying_signal", days_ago=200, source="TED"),
         _signal("proof_signal", days_ago=300, source="Finextra")],
        now=NOW_TS,
    )
    assert verdict.horizon == NEXT
    assert "none within 90 days" in verdict.reason


def test_two_recent_forming_market_signals_reach_next():
    verdict = aggregate_horizon(
        [_signal("competitor_move", days_ago=20, source="Digiday"),
         _signal("market_trend", days_ago=40, source="Finextra")],
        now=NOW_TS,
    )
    assert verdict.horizon == NEXT
    assert verdict.rule == "next_forming_market"


def test_one_forming_market_signal_is_not_enough_for_next():
    verdict = aggregate_horizon([_signal("competitor_move", days_ago=20)], now=NOW_TS)
    assert verdict.horizon == LATER


def test_signals_outside_the_recency_window_do_not_participate():
    verdict = aggregate_horizon(
        [_signal("buying_signal", days_ago=400, source="TED"),
         _signal("buying_signal", days_ago=500, source="UK Find a Tender")],
        now=NOW_TS,
    )
    assert verdict.horizon == LATER
    assert verdict.out_of_window_count == 2
    assert verdict.now_count == 0


def test_signal_without_a_date_does_not_participate():
    undated = _signal("buying_signal")
    undated["signal_date"] = None
    verdict = aggregate_horizon([undated], now=NOW_TS)
    assert verdict.horizon == LATER
    assert verdict.out_of_window_count == 1


# --- Part 4: per-signal priors and the confidence gate ---------------------


def test_regulation_prior_follows_the_event_date():
    in_force = signal_horizon_prior(
        "regulation", signal_date="2026-08-01", event_date="2026-01-01",
        event_date_precision="exact", confidence=0.9, now=NOW_TS,
    )
    soon = signal_horizon_prior(
        "regulation", signal_date="2026-08-01", event_date="2026-11-01",
        event_date_precision="exact", confidence=0.9, now=NOW_TS,
    )
    mid = signal_horizon_prior(
        "regulation", signal_date="2026-08-01", event_date="2027-08-01",
        event_date_precision="exact", confidence=0.9, now=NOW_TS,
    )
    far = signal_horizon_prior(
        "regulation", signal_date="2026-08-01", event_date="2031-01-01",
        event_date_precision="exact", confidence=0.9, now=NOW_TS,
    )
    assert (in_force.prior, soon.prior, mid.prior, far.prior) == (NOW, NOW, NEXT, LATER)


def test_regulation_without_a_usable_date_is_later():
    undated = signal_horizon_prior(
        "regulation", signal_date="2026-08-01", event_date=None,
        event_date_precision="none", confidence=0.9, now=NOW_TS,
    )
    vague = signal_horizon_prior(
        "regulation", signal_date="2026-08-01", event_date="2028-01-01",
        event_date_precision="none", confidence=0.9, now=NOW_TS,
    )
    assert undated.prior == LATER and vague.prior == LATER


def test_low_confidence_demotes_the_prior_one_step():
    gated = signal_horizon_prior("buying_signal", signal_date="2026-08-20", confidence=0.3, now=NOW_TS)
    assert gated.raw_prior == NOW and gated.prior == NEXT and gated.gated is True

    gated_next = signal_horizon_prior("market_trend", signal_date="2026-08-20", confidence=0.3, now=NOW_TS)
    assert gated_next.prior == LATER


def test_low_confidence_signals_can_never_trigger_now_alone():
    """The gate strips a Now prior, so two low-confidence tenders from two
    sources still cannot produce a Now verdict."""
    verdict = aggregate_horizon(
        [_signal("buying_signal", days_ago=2, source="TED", confidence=0.2),
         _signal("buying_signal", days_ago=3, source="UK Find a Tender", confidence=0.2)],
        now=NOW_TS,
    )
    assert verdict.horizon != NOW
    assert verdict.gated_count == 2


def test_thresholds_are_configuration_not_literals():
    tightened = signal_types.HorizonConfig(now_min_signals=3)
    signals = [_signal("buying_signal", days_ago=2, source="TED"),
               _signal("proof_signal", days_ago=2, source="Finextra")]
    assert aggregate_horizon(signals, now=NOW_TS).horizon == NOW
    assert aggregate_horizon(signals, now=NOW_TS, config=tightened).horizon == NEXT
