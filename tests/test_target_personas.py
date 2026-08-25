import json
import sqlite3
import sys
from pathlib import Path

import pytest

PIPELINE = Path(__file__).resolve().parents[1] / "Pipelineteamfile"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

from common.personas import (  # noqa: E402
    DEFAULT_WEIGHT_THRESHOLD,
    PERSONA_SCORE_FLOOR,
    PERSONA_SCORE_SCALE,
    VALID_WEIGHTS,
    PersonaConfigError,
    adjusted_score,
    build_index,
    coverage_report,
)
from opportunity_classifier.collector import storage as classifier_storage  # noqa: E402
from opportunity_classifier.collector import taxonomy as taxonomy_mod  # noqa: E402
from radar_v2.services import personas as persona_service  # noqa: E402

TAXONOMY = json.loads(taxonomy_mod.TAXONOMY_PATH.read_text(encoding="utf-8"))

EXPECTED_PERSONAS = [
    "cio", "it-network-executive", "cyber-executive", "cdo",
    "coo-production-executive", "cmo-cx-executive", "quality-manager",
    "industrial-safety-manager",
]


def test_persona_vocabulary_is_the_closed_eight():
    index = build_index(TAXONOMY)
    assert index.ids == EXPECTED_PERSONAS
    # The ninth EX/HR persona is a deliberate, documented gap - not an omission
    # to be repaired by whoever next edits the taxonomy.
    assert len(index.ids) == 8


def test_every_persona_reference_resolves_and_every_weight_is_a_tier():
    """Part 9.1: unknown slugs and off-tier weights must fail the build."""
    index = build_index(TAXONOMY)
    valid = set(index.ids)
    assert len(index.by_use_case) == len(TAXONOMY["use_cases"])
    assert len(index.by_domain) == len(TAXONOMY["business_domains"])
    for mapping in (index.by_use_case, index.by_domain):
        for entry_id, weights in mapping.items():
            assert weights, entry_id
            assert set(weights) <= valid, entry_id
            assert set(weights.values()) <= set(VALID_WEIGHTS), entry_id
    assert index.suppressions
    for rule in index.suppressions:
        assert rule["persona"] in valid
        assert rule["vertical"]


def test_unknown_persona_slug_fails_loudly():
    broken = json.loads(json.dumps(TAXONOMY))
    broken["use_cases"][0]["personas"] = [{"persona": "not-a-persona", "weight": 1.0}]
    with pytest.raises(PersonaConfigError):
        build_index(broken)


def test_off_tier_weight_fails_loudly():
    broken = json.loads(json.dumps(TAXONOMY))
    broken["use_cases"][0]["personas"] = [{"persona": "cio", "weight": 0.45}]
    with pytest.raises(PersonaConfigError):
        build_index(broken)


def test_use_case_without_personas_fails_loudly():
    broken = json.loads(json.dumps(TAXONOMY))
    broken["use_cases"][0].pop("personas")
    with pytest.raises(PersonaConfigError):
        build_index(broken)


def test_suppression_referencing_an_unknown_persona_fails_loudly():
    broken = json.loads(json.dumps(TAXONOMY))
    broken["persona_suppressions"] = [{"persona": "not-a-persona", "vertical": "Retail"}]
    with pytest.raises(PersonaConfigError):
        build_index(broken)


def test_combination_takes_the_max_not_the_sum():
    index = build_index(TAXONOMY)
    resolution = index.resolve("anomaly-detection", "ox-smart-industries", "Aerospace")
    # use case gives 0.3, the OX domain overlay gives 0.6 - the answer is 0.6,
    # never 0.9, and never above the primary tier.
    assert resolution.weight_of("coo-production-executive") == 0.6
    assert resolution.source_of("coo-production-executive") == "both"
    assert resolution.weight_of("cyber-executive") == 1.0
    assert resolution.source_of("cyber-executive") == "use_case"
    assert resolution.weight_of("quality-manager") == 0.3
    assert resolution.source_of("quality-manager") == "domain"
    assert max(entry.weight for entry in resolution.weights) <= 1.0


def test_only_the_primary_domain_contributes_to_the_overlay():
    index = build_index(TAXONOMY)
    with_overlay = index.resolve("sentiment-analysis", "cx-customer-experience", "Retail")
    without_overlay = index.resolve("sentiment-analysis", "ox-smart-industries", "Retail")
    assert with_overlay.weight_of("cmo-cx-executive") == 1.0
    assert without_overlay.weight_of("coo-production-executive") == 0.6
    assert without_overlay.weight_of("cmo-cx-executive") == 1.0


def test_absent_personas_are_zero_and_never_stored():
    index = build_index(TAXONOMY)
    resolution = index.resolve("sentiment-analysis", "cx-customer-experience", "Retail")
    assert resolution.weight_of("industrial-safety-manager") == 0.0
    assert all(entry.weight > 0 for entry in resolution.weights)


def test_suppression_zeroes_a_pair_regardless_of_derived_weight():
    """Part 6: the same use case keeps the persona in a plausible vertical and
    loses it in a suppressed one, whatever the tables produced."""
    index = build_index(TAXONOMY)
    kept = index.resolve("predictive-maintenance", "ox-smart-industries", "Manufacturing")
    zeroed = index.resolve("predictive-maintenance", "ox-smart-industries", "Retail")
    assert kept.weight_of("industrial-safety-manager") == 0.3
    assert zeroed.weight_of("industrial-safety-manager") == 0.0
    assert [entry.persona for entry in zeroed.suppressed] == ["industrial-safety-manager"]
    assert index.suppression_reason("industrial-safety-manager", "Retail")


def test_suppression_can_zero_a_primary_weight():
    index = build_index(TAXONOMY)
    zeroed = index.resolve("automated-inspection-defect-detection", "ox-smart-industries", "Media & Entertainment")
    assert zeroed.weight_of("quality-manager") == 0.0
    assert zeroed.weights == ()


def test_ranking_multiplier_matches_the_specified_tiers():
    assert adjusted_score(100, 1.0) == 100.0
    assert adjusted_score(100, 0.6) == 80.0
    assert adjusted_score(100, 0.3) == pytest.approx(65.0)
    assert adjusted_score(100, 0.0) == 50.0
    assert PERSONA_SCORE_FLOOR + PERSONA_SCORE_SCALE == 1.0


def test_ranking_dampens_it_does_not_invert():
    """Part 9.5: a much stronger unmatched space still outranks a weaker
    primary-persona one - the multiplier is not a hard filter in disguise."""
    assert adjusted_score(90, 0.0) > adjusted_score(40, 1.0)
    # but persona does reorder two comparable spaces
    assert adjusted_score(60, 1.0) > adjusted_score(70, 0.0)


def _space_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE articles(id INTEGER PRIMARY KEY, vertical TEXT)")
    classifier_storage.ensure_schema(connection)
    connection.executemany(
        "INSERT INTO opportunity_spaces(vertical,use_case_id,technology_id,article_count,"
        "linked_article_ids,first_seen_at,last_updated_at,primary_domain) "
        "VALUES(?,?,?,1,'[]','now','now',?)",
        [
            ("Manufacturing", "predictive-maintenance", "digital-twin", "ox-smart-industries"),
            ("Retail", "predictive-maintenance", "digital-twin", "ox-smart-industries"),
        ],
    )
    connection.commit()
    return connection


def test_backfill_is_idempotent_and_recomputable():
    connection = _space_database()
    first = classifier_storage.backfill_target_personas(connection)
    rows = connection.execute(
        "SELECT space_id,persona_id,weight,source FROM opportunity_space_personas ORDER BY 1,2"
    ).fetchall()
    assert first["total_spaces"] == 2
    assert len(rows) == 3 + 2  # Retail loses the suppressed industrial safety pair

    connection.execute("DELETE FROM opportunity_space_personas")
    second = classifier_storage.backfill_target_personas(connection)
    assert second == first
    assert connection.execute(
        "SELECT space_id,persona_id,weight,source FROM opportunity_space_personas ORDER BY 1,2"
    ).fetchall() == rows


def test_backfill_never_writes_an_explicit_zero():
    connection = _space_database()
    classifier_storage.backfill_target_personas(connection)
    assert connection.execute(
        "SELECT COUNT(*) FROM opportunity_space_personas WHERE weight<=0"
    ).fetchone()[0] == 0


def test_coverage_report_flags_a_thin_persona():
    index = build_index(TAXONOMY)
    resolutions = [index.resolve("sentiment-analysis", "cx-customer-experience", "Retail")] * 20
    report = coverage_report(index, resolutions)
    assert report["counts"]["cmo-cx-executive"] == 20
    assert set(report["low_coverage"]) == set(index.ids) - {"cmo-cx-executive"}


def test_coverage_report_counts_suppressions_that_fired():
    index = build_index(TAXONOMY)
    resolutions = [index.resolve("predictive-maintenance", "ox-smart-industries", "Retail")] * 3
    report = coverage_report(index, resolutions)
    assert report["suppressed_total"] == 3
    assert report["suppressions_fired"] == {"industrial-safety-manager": 3}


def _item(relevance: int, weights: list[tuple[str, float]]) -> dict:
    return {
        "relevance": relevance, "article_count": 1,
        "persona_weights": [
            {"id": pid, "label": persona_service.label(pid), "weight": weight, "source": "use_case"}
            for pid, weight in weights
        ],
    }


def test_app_service_reads_weights_and_thresholds():
    item = _item(80, [("cio", 1.0), ("cdo", 0.3)])
    assert persona_service.weight_of(item, "cio") == 1.0
    assert persona_service.weight_of(item, "cmo-cx-executive") == 0.0
    assert persona_service.passes(item, "cdo") is True
    assert persona_service.passes(item, "cdo", 0.6) is False   # Sales mode threshold
    assert persona_service.passes(item, "") is True            # no persona is no constraint
    assert persona_service.passes(item, "cmo-cx-executive") is False


def test_app_service_filter_is_or_within_the_dimension():
    item = _item(80, [("cio", 1.0)])
    assert persona_service.passes_any(item, []) is True
    assert persona_service.passes_any(item, ["cdo", "cio"]) is True
    assert persona_service.passes_any(item, ["cdo", "cmo-cx-executive"]) is False
    assert persona_service.passes_any(item, ["cdo", "cio"], 0.6) is True


def test_app_service_ranking_uses_the_dampened_multiplier():
    primary = _item(60, [("cio", 1.0)])
    unmatched = _item(70, [])
    assert persona_service.persona_adjusted_score(primary, "cio") == 60.0
    assert persona_service.persona_adjusted_score(unmatched, "cio") == 35.0
    assert [item["relevance"] for item in persona_service.sort_by_persona([unmatched, primary], "cio")] == [60, 70]
    # No persona selected - base score, unadjusted.
    assert persona_service.persona_adjusted_score(unmatched, "") == 70.0


def test_app_service_options_come_from_the_taxonomy():
    assert [option["id"] for option in persona_service.options()] == [
        entry["id"] for entry in TAXONOMY["personas"]
    ]
    assert persona_service.DEFAULT_WEIGHT_THRESHOLD == DEFAULT_WEIGHT_THRESHOLD


def test_app_fallback_derivation_matches_the_pipeline():
    derived = persona_service.derive("predictive-maintenance", "ox-smart-industries", "Retail")
    assert [entry["id"] for entry in derived] == ["coo-production-executive", "quality-manager"]
    assert derived[0]["weight"] == 1.0
    assert persona_service.derive("not-a-use-case", "cloud", "Retail") == []
