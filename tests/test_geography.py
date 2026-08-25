import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PIPELINE = Path(__file__).resolve().parents[1] / "Pipelineteamfile"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

from common.geography import (  # noqa: E402
    GLOBAL_REGION,
    GeographyConfigError,
    aggregate_geography,
    build_index,
    coverage_report,
)
from opportunity_classifier.collector import geo_route  # noqa: E402
from opportunity_classifier.collector import taxonomy as taxonomy_mod  # noqa: E402
from radar_v2.services import geography as geography_service  # noqa: E402
from radar_v2.state import RadarState  # noqa: E402

TAXONOMY = json.loads(taxonomy_mod.TAXONOMY_PATH.read_text(encoding="utf-8"))
INDEX = build_index(TAXONOMY)

# Part 1's table, verbatim. Written out here rather than read from taxonomy.json
# so the test fails if the configuration is "corrected" toward convention.
PART_ONE = {
    "benelux": ["NL", "BE", "LU"],
    "germany": ["DE"],
    "france": ["FR"],
    "southern-europe": ["IT", "ES", "PT", "IL"],
    "dach": ["CH", "AT"],
    "uk-ireland": ["GB", "IE"],
    "nordics": ["NO", "SE", "DK", "FI", "IS"],
    "eastern-europe": [
        "PL", "CZ", "SK", "HU", "RO", "BG", "SI", "HR", "EE", "LV", "LT", "UA", "RS",
    ],
    "north-america": ["US", "CA", "MX"],
}


def test_configured_taxonomy_validates():
    """Part 6.1: the region configuration must load, carry the global region and
    every continent fallback target, and claim no country twice."""
    assert GLOBAL_REGION in INDEX.ids
    claimed = {}
    for entry in INDEX.regions:
        for code in entry.get("countries", []):
            assert code not in claimed, code
            claimed[code] = entry["id"]


@pytest.mark.parametrize(
    "region_id,codes", [(region, codes) for region, codes in PART_ONE.items()]
)
def test_part_one_countries_roll_up_correctly(region_id, codes):
    for code in codes:
        assert INDEX.region_for(code) == region_id, code


def test_deliberate_business_groupings_are_not_corrected_to_convention():
    """The three decisions the spec calls out as easy to auto-correct back:
    DACH is Switzerland+Austria only, Germany stands alone, France stands
    alone."""
    assert INDEX.by_country["DE"] == "germany"
    assert INDEX.by_country["FR"] == "france"
    assert sorted(code for code, region in INDEX.by_country.items() if region == "dach") == ["AT", "CH"]
    assert "DE" not in [code for code, region in INDEX.by_country.items() if region == "dach"]
    assert INDEX.by_country["FR"] not in ("benelux", "southern-europe", "dach")


def test_country_claimed_by_two_regions_fails_loudly():
    broken = json.loads(json.dumps(TAXONOMY))
    broken["regions"][1]["countries"].append("NL")  # already in benelux
    with pytest.raises(GeographyConfigError):
        build_index(broken)


def test_unknown_iso_code_in_config_fails_loudly():
    broken = json.loads(json.dumps(TAXONOMY))
    broken["regions"][0]["countries"].append("ZZ")
    with pytest.raises(GeographyConfigError):
        build_index(broken)


def test_missing_global_region_fails_loudly():
    broken = json.loads(json.dumps(TAXONOMY))
    broken["regions"] = [r for r in broken["regions"] if r["id"] != GLOBAL_REGION]
    with pytest.raises(GeographyConfigError):
        build_index(broken)


@pytest.mark.parametrize("code,region", [
    ("BR", "south-america"), ("NG", "africa"), ("JP", "asia"),
    ("AU", "oceania"), ("GL", "north-america"),
])
def test_continent_fallback_for_countries_outside_part_one(code, region):
    assert INDEX.region_for(code) == region


@pytest.mark.parametrize("code", ["GR", "CY", "MT", "TR", "RU", "AL", "MD", "BY"])
def test_european_countries_outside_part_one_are_reported_not_resolved(code):
    """Part 6.2: a European country the table does not list must resolve to
    nothing so it surfaces as unresolved. Falling back to `asia` by geographic
    technicality, or to `global` by convenience, would be exactly the silent
    resolution the spec forbids."""
    assert INDEX.region_for(code) == ""
    resolution = INDEX.resolve([code])
    assert resolution.regions == ()
    assert code in resolution.unresolved


@pytest.mark.parametrize("raw,expected", [
    ("SWE", "SE"),      # TED emits ISO alpha-3
    ("GBR", "GB"),
    ("EL", "GR"),       # CORDIS emits the EU code for Greece
    ("UK", "GB"),       # ...and for the United Kingdom
    ("IT", "IT"),
    ("Italy", "IT"),    # CORDIS coordinated_in is an English name
    ("Czechia", "CZ"),
    ("nonsense", None),
])
def test_country_token_normalisation(raw, expected):
    assert INDEX.normalise_country(raw) == expected


def test_multi_country_signal_keeps_every_country_and_region():
    """A CORDIS consortium is genuinely multi-country - storing only the first
    participant would lose most of the project's geography."""
    resolution = INDEX.resolve(["IT", "EL", "BE", "ES", "IT"])
    assert resolution.countries == ("BE", "ES", "GR", "IT")
    assert set(resolution.regions) == {"benelux", "southern-europe"}
    assert "GR" in resolution.unresolved


def test_empty_countries_is_a_valid_answer_and_never_becomes_global():
    resolution = INDEX.resolve([])
    assert resolution.countries == ()
    assert resolution.regions == ()
    assert resolution.region_override == ""
    assert resolution.is_empty


def test_region_override_is_a_separate_path_from_countries():
    resolution = INDEX.resolve([], region_override=GLOBAL_REGION)
    assert resolution.countries == ()
    assert resolution.regions == (GLOBAL_REGION,)
    assert not resolution.is_empty


def test_low_confidence_geography_is_flagged_not_dropped():
    """Part 3's confidence gate: below 0.5 the countries are kept and marked."""
    resolution = INDEX.resolve(["DE"], confidence=0.3)
    assert resolution.countries == ("DE",)
    assert resolution.regions == ("germany",)
    assert resolution.low_confidence


def _signal(countries, days_ago, override=None, confidence=1.0):
    """A signal shaped exactly as storage.space_geography_signals emits one, so
    the aggregation is exercised on the real row shape rather than a subset."""
    resolution = INDEX.resolve(countries)
    return {
        "countries": list(resolution.countries),
        "regions": list(resolution.regions),
        "unresolved": list(resolution.unresolved),
        "region_override": override,
        "geography_confidence": confidence,
        "signal_date": (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat(),
    }


def test_space_geography_is_the_union_of_its_signals():
    verdict = aggregate_geography(INDEX, [_signal(["DE"], 10), _signal(["NL", "BE"], 40)])
    assert set(verdict.regions) == {"germany", "benelux"}
    assert verdict.countries == ("BE", "DE", "NL")


def test_stale_signals_do_not_contribute_geography():
    """Part 4's recency window: a three-year-old signal's country must not
    dominate a space."""
    verdict = aggregate_geography(INDEX, [_signal(["DE"], 20), _signal(["BR"], 1100)])
    assert set(verdict.regions) == {"germany"}
    assert verdict.out_of_window_signals == 1


def test_primary_region_is_the_most_evidenced_one():
    verdict = aggregate_geography(
        INDEX, [_signal(["DE"], 5), _signal(["DE"], 30), _signal(["NL"], 10)]
    )
    assert verdict.primary_region == "germany"


def test_primary_region_tie_breaks_on_recency_then_country_count():
    """One multi-country signal gives every region it touches the same count and
    the same date, so without the country-count tie-break the primary would fall
    to whichever region taxonomy.json happens to list first."""
    verdict = aggregate_geography(INDEX, [_signal(["BE", "NO", "SE", "DK"], 10)])
    assert verdict.primary_region == "nordics"


def test_space_with_no_geography_is_valid_and_not_excluded():
    verdict = aggregate_geography(INDEX, [_signal([], 10), _signal([], 20)])
    assert verdict.primary_region == ""
    assert verdict.regions == ()
    assert verdict.untagged_signals == 2


def test_tagged_global_and_untagged_stay_distinct():
    tagged = aggregate_geography(INDEX, [_signal([], 10, override=GLOBAL_REGION)])
    untagged = aggregate_geography(INDEX, [_signal([], 10)])
    assert tagged.regions == (GLOBAL_REGION,)
    assert tagged.primary_region == GLOBAL_REGION
    assert untagged.regions == ()
    assert untagged.primary_region == ""


def test_coverage_report_surfaces_unresolved_countries():
    verdicts = [aggregate_geography(INDEX, [_signal(["GR", "DE"], 10)])]
    report = coverage_report(INDEX, verdicts)
    assert "GR" in report["unresolved_countries"]
    assert report["no_geography"] == 0


def test_ted_alpha3_array_is_extracted_and_normalised():
    """TED's live shape: a per-lot array of ISO alpha-3 codes, not a single
    alpha-2 code."""
    extra = json.dumps({"buyer_country": ["SWE"]})
    resolution, assignment = geo_route.resolve(INDEX, "ted", extra)
    assert assignment.source_field == "extra.buyer_country"
    assert resolution.countries == ("SE",)
    assert resolution.regions == ("nordics",)


@pytest.mark.parametrize("source_type,code,region", [
    ("ocds_uk", "GB", "uk-ireland"),
    ("ocds_ua", "UA", "eastern-europe"),
])
def test_ocds_single_country_feeds(source_type, code, region):
    resolution, _ = geo_route.resolve(INDEX, source_type, json.dumps({"buyer_country": code}))
    assert resolution.regions == (region,)


def test_sam_gov_reads_the_field_rather_than_hardcoding_north_america():
    """The spec is explicit that SAM.gov resolving to North America in almost
    every case must not become a hardcoded assumption."""
    resolution, _ = geo_route.resolve(
        INDEX, "sam_gov", json.dumps({"place_of_performance_country": "DE"})
    )
    assert resolution.regions == ("germany",)
    assert geo_route.extract_countries("sam_gov", json.dumps({})) is None


def test_cordis_participant_list_is_multi_valued():
    status = {"status": "SIGNED", "participant_countries": ["IT", "EL", "BE", "ES"]}
    resolution, assignment = geo_route.resolve(INDEX, "cordis", json.dumps({}), status)
    assert assignment.source_field == "project.organization.address.country"
    assert set(resolution.regions) == {"southern-europe", "benelux"}
    assert "GR" in resolution.unresolved


def test_cordis_falls_back_to_the_coordinator_country_at_lower_confidence():
    extra = json.dumps({"coordinated_in": "Netherlands"})
    resolution, assignment = geo_route.resolve(INDEX, "cordis", extra)
    assert resolution.regions == ("benelux",)
    assert assignment.confidence < geo_route.DETERMINISTIC_CONFIDENCE


def test_rss_has_no_deterministic_geography():
    assert geo_route.resolve(INDEX, "rss", json.dumps({})) is None


def _item(regions):
    return {"regions": list(regions)}


def test_app_filter_is_or_within_the_dimension():
    items = [_item(["benelux"]), _item(["nordics"]), _item(["asia"])]
    matched = [item for item in items if geography_service.passes_any(item, ["benelux", "nordics"])]
    assert len(matched) == 2


def test_app_filter_matches_a_region_anywhere_in_the_set():
    assert geography_service.passes_any(_item(["germany", "benelux"]), ["benelux"])


def test_empty_app_filter_is_no_constraint():
    assert geography_service.passes_any(_item([]), [])


def test_global_filter_does_not_match_untagged_spaces():
    """Part 5: filtering by global returns only spaces explicitly resolved
    there, never the far larger set that merely lacks geography."""
    untagged = _item([])
    tagged = _item([GLOBAL_REGION])
    assert not geography_service.passes_any(untagged, [GLOBAL_REGION])
    assert geography_service.passes_any(tagged, [GLOBAL_REGION])
    assert geography_service.is_untagged(untagged)
    assert geography_service.is_tagged_global(tagged)
    assert not geography_service.is_tagged_global(untagged)


def test_untagged_space_displays_as_unspecified():
    assert geography_service.primary_label("") == geography_service.UNSPECIFIED_LABEL
    assert geography_service.primary_label(GLOBAL_REGION) != geography_service.UNSPECIFIED_LABEL


def test_region_filter_options_come_from_the_taxonomy():
    assert [option["id"] for option in geography_service.options()] == INDEX.ids


def test_state_toggles_and_clears_the_region_filter():
    state = RadarState(region_filter=[])
    state.toggle_region_filter("benelux")
    state.toggle_region_filter("nordics")
    assert sorted(state.region_filter) == ["benelux", "nordics"]
    state.toggle_region_filter("benelux")
    assert state.region_filter == ["nordics"]
    state.clear_region_filter()
    assert state.region_filter == []
