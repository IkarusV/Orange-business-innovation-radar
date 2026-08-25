import json
import sqlite3
import sys
from pathlib import Path

import pytest

PIPELINE = Path(__file__).resolve().parents[1] / "Pipelineteamfile"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

from common.business_domains import DomainConfigError, build_index, coverage_report  # noqa: E402
from opportunity_classifier.collector import storage as classifier_storage  # noqa: E402
from opportunity_classifier.collector import taxonomy as taxonomy_mod  # noqa: E402
from radar_v2.state import RadarState  # noqa: E402

TAXONOMY = json.loads(taxonomy_mod.TAXONOMY_PATH.read_text(encoding="utf-8"))


def test_configured_taxonomy_validates():
    """Part 6.1: every technology and every use case carrying a domains array
    must reference only the six valid slugs, and no technology may be unmapped."""
    index = build_index(TAXONOMY)
    assert len(index.ids) == 6
    assert len(index.by_technology) == len(TAXONOMY["technologies"])
    valid = set(index.ids)
    for mapping in (index.by_technology, index.by_use_case):
        for entry_id, domain_ids in mapping.items():
            assert domain_ids, entry_id
            assert set(domain_ids) <= valid, entry_id


def test_unknown_domain_slug_fails_loudly():
    broken = json.loads(json.dumps(TAXONOMY))
    broken["technologies"][0]["domains"] = ["not-a-domain"]
    with pytest.raises(DomainConfigError):
        build_index(broken)


def test_technology_without_domains_fails_loudly():
    broken = json.loads(json.dumps(TAXONOMY))
    broken["technologies"][0].pop("domains")
    with pytest.raises(DomainConfigError):
        build_index(broken)


def test_resolution_is_the_union_with_a_technology_primary():
    index = build_index(TAXONOMY)
    resolution = index.resolve("machine-learning", "fraud-detection")
    assert resolution.primary == "cloud"  # first technology entry, never a use-case one
    assert set(resolution.domains) == {"cloud", "ox-smart-industries", "cybersecurity"}
    assert resolution.domains[0] == resolution.primary
    assert resolution.source_of("cybersecurity") == "use_case"
    assert resolution.source_of("cloud") == "technology"


def test_use_case_without_domains_contributes_nothing():
    index = build_index(TAXONOMY)
    resolution = index.resolve("digital-twin", "predictive-maintenance")
    assert resolution.domains == ("ox-smart-industries",)


def _space_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE articles(id INTEGER PRIMARY KEY, vertical TEXT)")
    classifier_storage.ensure_schema(connection)
    connection.executemany(
        "INSERT INTO opportunity_spaces(vertical,use_case_id,technology_id,article_count,"
        "linked_article_ids,first_seen_at,last_updated_at) VALUES(?,?,?,1,'[]','now','now')",
        [
            ("Manufacturing", "predictive-maintenance", "digital-twin"),
            ("Financial services", "fraud-detection", "machine-learning"),
        ],
    )
    connection.commit()
    return connection


def test_backfill_is_idempotent_and_recomputable():
    connection = _space_database()
    first = classifier_storage.backfill_business_domains(connection)
    rows = connection.execute("SELECT COUNT(*) FROM opportunity_space_domains").fetchone()[0]
    assert rows == 1 + 3
    assert first["total_spaces"] == 2

    connection.execute("DELETE FROM opportunity_space_domains")
    second = classifier_storage.backfill_business_domains(connection)
    assert second == first
    assert connection.execute("SELECT COUNT(*) FROM opportunity_space_domains").fetchone()[0] == rows

    primary = connection.execute(
        "SELECT s.primary_domain FROM opportunity_spaces s WHERE s.technology_id='machine-learning'"
    ).fetchone()[0]
    assert primary == "cloud"


def test_coverage_report_flags_a_thin_domain():
    index = build_index(TAXONOMY)
    resolutions = [index.resolve("digital-twin", "predictive-maintenance")] * 20
    report = coverage_report(index, resolutions)
    assert report["union"]["ox-smart-industries"] == 20
    assert set(report["low_coverage"]) == set(index.ids) - {"ox-smart-industries"}
    assert report["set_sizes"] == {1: 20}


def _space(space_id: int, vertical: str, horizon: str, domain_ids: list) -> dict:
    return {
        "id": space_id, "vertical": vertical, "horizon": horizon, "domains": domain_ids,
        "use_case": "", "technology": "", "summary": "",
    }


def test_domain_filter_is_or_within_and_and_across_dimensions():
    state = RadarState()
    state.opportunities = [
        _space(1, "Manufacturing", "Now", ["cloud"]),
        _space(2, "Manufacturing", "Now", ["cybersecurity", "cloud"]),
        _space(3, "Public sector", "Later", ["cybersecurity"]),
        _space(4, "Manufacturing", "Now", ["ex-employee-experience"]),
    ]
    assert len(state.visible_opportunities) == 4  # empty selection is no constraint

    state.toggle_domain_filter("cloud")
    state.toggle_domain_filter("cybersecurity")
    assert [item["id"] for item in state.visible_opportunities] == [1, 2, 3]

    state.vertical_filter = "Manufacturing"
    assert [item["id"] for item in state.visible_opportunities] == [1, 2]

    state.toggle_domain_filter("cloud")
    assert [item["id"] for item in state.visible_opportunities] == [2]

    state.clear_domain_filter()
    assert [item["id"] for item in state.visible_opportunities] == [1, 2, 4]


def test_domain_filter_matches_a_non_primary_domain():
    state = RadarState()
    state.opportunities = [_space(1, "Manufacturing", "Now", ["cloud", "ox-smart-industries"])]
    state.toggle_domain_filter("ox-smart-industries")
    assert len(state.visible_opportunities) == 1


def test_filter_options_come_from_the_taxonomy():
    state = RadarState()
    assert [option["id"] for option in state.domain_filter_options] == [
        entry["id"] for entry in TAXONOMY["business_domains"]
    ]
    assert all(option["selected"] is False for option in state.domain_filter_options)
