"""Geography: the closed region vocabulary, the country->region rollup, and the
aggregation of a space's geography from its signals.

Same shape as common/business_domains.py and common/personas.py - the rules live
here as the single source of truth, imported by both the pipeline (which
resolves and persists) and the app (which reads and filters).

Two tables, deliberately in two different places:

    taxonomy.json "regions"   - the business grouping. Which countries belong to
                                Benelux, whether Germany stands alone, whether
                                DACH means Switzerland+Austria. A non-engineer
                                edits this, and "extend eastern-europe when a
                                live signal names a country not on the list" is
                                a config edit plus a backfill rerun.
    ISO tables below          - mechanical. Alpha-2/alpha-3 equivalence and the
                                continent of each ISO code are facts, not
                                business decisions, so they live in Python like
                                common/trust.py's HARDCODED_SOURCES.

The continent fallback only covers the five coarse non-European regions. A
European country that is not in the taxonomy's own lists resolves to NOTHING
and is reported as unresolved rather than being pushed into `asia` by geographic
technicality or into `global` by convenience - silently resolving it is exactly
what the spec forbids.

Resolution is mechanical for TED/OCDS/CORDIS/SAM.gov, where the record carries
the country, and inferred by the classifier only for RSS and GNews, where the
country exists solely in free text. Nothing here ever guesses a country.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from common.signal_types import parse_date

# The catch-all region for EU-wide regulation and worldwide statements. Set by
# the classifier's region_override, never inferred from an empty country list -
# "tagged global" and "no geography" are different states.
GLOBAL_REGION = "global"

# Below this the geography is kept and flagged, never dropped: an uncertain
# country tag is still more useful for a filter than none. Mirrors the
# signal-type confidence gate, but it demotes nothing - it only marks.
CONFIDENCE_GATE = 0.5

# Same recency window the horizon rules use: a three-year-old signal's country
# must not dominate a space's geography.
RECENCY_WINDOW_DAYS = 365

# A region holding no space at all after a backfill is a coverage signal, not
# necessarily an error - the corpus genuinely may not reach every region.
LOW_COVERAGE_SHARE = 0.02

DETERMINISTIC = "deterministic"
INFERRED = "inferred"

# ISO 3166-1: "alpha2/alpha3" per country, grouped by the continent used for the
# coarse fallback. "europe" has no fallback region on purpose - see the module
# docstring.
_ISO_TABLE = {
    "europe": (
        "AD/AND AL/ALB AT/AUT AX/ALA BA/BIH BE/BEL BG/BGR BY/BLR CH/CHE CY/CYP CZ/CZE "
        "DE/DEU DK/DNK EE/EST ES/ESP FI/FIN FO/FRO FR/FRA GB/GBR GG/GGY GI/GIB GR/GRC "
        "HR/HRV HU/HUN IE/IRL IM/IMN IS/ISL IT/ITA JE/JEY LI/LIE LT/LTU LU/LUX LV/LVA "
        "MC/MCO MD/MDA ME/MNE MK/MKD MT/MLT NL/NLD NO/NOR PL/POL PT/PRT RO/ROU RS/SRB "
        "RU/RUS SE/SWE SI/SVN SJ/SJM SK/SVK SM/SMR TR/TUR UA/UKR VA/VAT XK/XKX"
    ),
    "north-america": (
        "AG/ATG AI/AIA AW/ABW BB/BRB BL/BLM BM/BMU BQ/BES BS/BHS BZ/BLZ CA/CAN CR/CRI "
        "CU/CUB CW/CUW DM/DMA DO/DOM GD/GRD GL/GRL GP/GLP GT/GTM HN/HND HT/HTI JM/JAM "
        "KN/KNA KY/CYM LC/LCA MF/MAF MQ/MTQ MS/MSR MX/MEX NI/NIC PA/PAN PM/SPM PR/PRI "
        "SV/SLV SX/SXM TC/TCA TT/TTO US/USA VC/VCT VG/VGB VI/VIR"
    ),
    "south-america": (
        "AR/ARG BO/BOL BR/BRA CL/CHL CO/COL EC/ECU FK/FLK GF/GUF GY/GUY PE/PER PY/PRY "
        "SR/SUR UY/URY VE/VEN"
    ),
    "africa": (
        "AO/AGO BF/BFA BI/BDI BJ/BEN BW/BWA CD/COD CF/CAF CG/COG CI/CIV CM/CMR CV/CPV "
        "DJ/DJI DZ/DZA EG/EGY EH/ESH ER/ERI ET/ETH GA/GAB GH/GHA GM/GMB GN/GIN GQ/GNQ "
        "GW/GNB KE/KEN KM/COM LR/LBR LS/LSO LY/LBY MA/MAR MG/MDG ML/MLI MR/MRT MU/MUS "
        "MW/MWI MZ/MOZ NA/NAM NE/NER NG/NGA RE/REU RW/RWA SC/SYC SD/SDN SH/SHN SL/SLE "
        "SN/SEN SO/SOM SS/SSD ST/STP SZ/SWZ TD/TCD TG/TGO TN/TUN TZ/TZA UG/UGA YT/MYT "
        "ZA/ZAF ZM/ZMB ZW/ZWE"
    ),
    "asia": (
        "AE/ARE AF/AFG AM/ARM AZ/AZE BD/BGD BH/BHR BN/BRN BT/BTN CN/CHN GE/GEO HK/HKG "
        "ID/IDN IL/ISR IN/IND IQ/IRQ IR/IRN JO/JOR JP/JPN KG/KGZ KH/KHM KP/PRK KR/KOR "
        "KW/KWT KZ/KAZ LA/LAO LB/LBN LK/LKA MM/MMR MN/MNG MO/MAC MV/MDV MY/MYS NP/NPL "
        "OM/OMN PH/PHL PK/PAK PS/PSE QA/QAT SA/SAU SG/SGP SY/SYR TH/THA TJ/TJK TL/TLS "
        "TM/TKM TW/TWN UZ/UZB VN/VNM YE/YEM"
    ),
    "oceania": (
        "AS/ASM AU/AUS CK/COK FJ/FJI FM/FSM GU/GUM KI/KIR MH/MHL MP/MNP NC/NCL NF/NFK "
        "NR/NRU NU/NIU NZ/NZL PF/PYF PG/PNG PN/PCN PW/PLW SB/SLB TK/TKL TO/TON TV/TUV "
        "VU/VUT WF/WLF WS/WSM"
    ),
}

# Continents that are themselves a region id. "europe" is absent: a European
# country only ever resolves through the taxonomy's own lists.
FALLBACK_CONTINENT_REGIONS = {
    "north-america", "south-america", "africa", "asia", "oceania",
}


def _build_iso_tables():
    by_continent, alpha3, names = {}, {}, set()
    for continent, codes in _ISO_TABLE.items():
        for pair in codes.split():
            a2, a3 = pair.split("/")
            by_continent[a2] = continent
            alpha3[a3] = a2
            names.add(a2)
    return by_continent, alpha3, names


CONTINENT_BY_ALPHA2, ALPHA2_BY_ALPHA3, ISO_ALPHA2 = _build_iso_tables()

# EU/Eurostat codes that are not ISO alpha-2. CORDIS returns EL for Greece and
# UK for the United Kingdom; both appear in live participant data.
CODE_ALIASES = {"EL": "GR", "UK": "GB", "XI": "GB"}

# CORDIS's `coordinated_in` is an English country name, not a code - the only
# geography the search API returns without a per-project fetch. Only the names
# actually observable in this corpus are listed; an unknown name resolves to
# nothing and is reported, exactly like an unknown code.
COUNTRY_NAMES = {
    "albania": "AL", "austria": "AT", "belgium": "BE", "bosnia and herzegovina": "BA",
    "bulgaria": "BG", "canada": "CA", "croatia": "HR", "cyprus": "CY",
    "czechia": "CZ", "czech republic": "CZ", "denmark": "DK", "estonia": "EE",
    "finland": "FI", "france": "FR", "georgia": "GE", "germany": "DE", "greece": "GR",
    "hungary": "HU", "iceland": "IS", "ireland": "IE", "israel": "IL", "italy": "IT",
    "latvia": "LV", "lithuania": "LT", "luxembourg": "LU", "malta": "MT", "mexico": "MX",
    "moldova": "MD", "montenegro": "ME", "netherlands": "NL", "north macedonia": "MK",
    "norway": "NO", "poland": "PL", "portugal": "PT", "romania": "RO", "serbia": "RS",
    "slovakia": "SK", "slovenia": "SI", "spain": "ES", "sweden": "SE",
    "switzerland": "CH", "turkey": "TR", "türkiye": "TR", "ukraine": "UA",
    "united kingdom": "GB", "united states": "US",
}


class GeographyConfigError(ValueError):
    """Raised when taxonomy.json carries an unusable region configuration.
    Deliberately fatal: a duplicate country across two regions or an unknown ISO
    code would produce spaces the geography filter can never return correctly."""


@dataclass(frozen=True)
class GeographyResolution:
    """One signal's resolved geography. Unresolved tokens are carried rather
    than dropped so Part 6.2's "report, do not silently resolve" is a property
    of the data structure and not of a log line someone has to notice."""
    countries: tuple
    regions: tuple
    unresolved: tuple
    region_override: str = ""
    confidence: float = 1.0
    assigned_by: str = DETERMINISTIC

    @property
    def low_confidence(self) -> bool:
        return self.confidence < CONFIDENCE_GATE

    @property
    def is_empty(self) -> bool:
        return not self.countries and not self.regions


class GeographyIndex:
    """Validated view over taxonomy.json's region configuration."""

    def __init__(self, regions: list):
        self.regions = regions
        self.ids = [entry["id"] for entry in regions]
        self.labels = {entry["id"]: entry["label"] for entry in regions}
        self.by_country = {}
        for entry in regions:
            for code in entry.get("countries", []):
                self.by_country[code] = entry["id"]
        self._order = {region_id: position for position, region_id in enumerate(self.ids)}

    def label(self, region_id: str) -> str:
        return self.labels.get(region_id, region_id)

    def options(self) -> list:
        """Vocabulary in taxonomy order - what a region picker renders."""
        return [{"id": entry["id"], "label": entry["label"]} for entry in self.regions]

    def countries_of(self, region_id: str) -> tuple:
        return tuple(
            entry.get("countries", []) for entry in self.regions if entry["id"] == region_id
        )[0] if region_id in self._order else ()

    def normalise_country(self, raw) -> Optional[str]:
        """Any of the shapes the four structured sources and the classifier
        actually emit, to ISO alpha-2: alpha-2 (CORDIS participants, RSS),
        alpha-3 (TED buyer-country, e.g. 'SWE'), an EU code (CORDIS 'EL'), or an
        English country name (CORDIS 'coordinated_in'). None when the token is
        not a country this module recognises."""
        if not raw:
            return None
        token = str(raw).strip()
        if not token:
            return None
        upper = token.upper()
        if upper in CODE_ALIASES:
            return CODE_ALIASES[upper]
        if len(upper) == 2 and upper in ISO_ALPHA2:
            return upper
        if len(upper) == 3 and upper in ALPHA2_BY_ALPHA3:
            return ALPHA2_BY_ALPHA3[upper]
        return COUNTRY_NAMES.get(token.lower())

    def region_for(self, alpha2: str) -> str:
        """Region id for an ISO alpha-2 code. The taxonomy's own lists win; a
        code outside them falls back to its continent, but only for the five
        coarse non-European regions. A European code not in the taxonomy returns
        "" and the caller reports it."""
        if alpha2 in self.by_country:
            return self.by_country[alpha2]
        continent = CONTINENT_BY_ALPHA2.get(alpha2, "")
        return continent if continent in FALLBACK_CONTINENT_REGIONS else ""

    def resolve(
        self,
        raw_countries: Iterable,
        region_override: Optional[str] = None,
        confidence: float = 1.0,
        assigned_by: str = DETERMINISTIC,
    ) -> GeographyResolution:
        """One signal's countries and regions. Multi-country by construction -
        a CORDIS consortium yields every participant country and every region
        they roll up to, not just the first."""
        countries, regions, unresolved = [], [], []
        for raw in raw_countries or ():
            alpha2 = self.normalise_country(raw)
            if alpha2 is None:
                token = str(raw).strip()
                if token and token not in unresolved:
                    unresolved.append(token)
                continue
            if alpha2 not in countries:
                countries.append(alpha2)
            region = self.region_for(alpha2)
            if not region:
                if alpha2 not in unresolved:
                    unresolved.append(alpha2)
                continue
            if region not in regions:
                regions.append(region)
        override = (region_override or "").strip()
        if override:
            if override not in self._order:
                unresolved.append(override)
                override = ""
            elif override not in regions:
                regions.append(override)
        regions.sort(key=lambda region_id: self._order.get(region_id, 99))
        return GeographyResolution(
            countries=tuple(sorted(countries)),
            regions=tuple(regions),
            unresolved=tuple(unresolved),
            region_override=override,
            confidence=float(confidence),
            assigned_by=assigned_by,
        )


def _validate_region(entry: dict, seen_ids: set, seen_countries: dict) -> None:
    region_id = entry.get("id")
    if not region_id:
        raise GeographyConfigError(f"region entry has no id: {entry}")
    if not entry.get("label"):
        raise GeographyConfigError(f"region '{region_id}' has no label")
    if region_id in seen_ids:
        raise GeographyConfigError(f"duplicate region id: {region_id}")
    seen_ids.add(region_id)
    countries = entry.get("countries", [])
    if not isinstance(countries, list):
        raise GeographyConfigError(f"region '{region_id}' has a malformed 'countries' array")
    for code in countries:
        if code not in ISO_ALPHA2:
            raise GeographyConfigError(
                f"region '{region_id}' lists '{code}', which is not an ISO 3166-1 alpha-2 code"
            )
        if code in seen_countries:
            raise GeographyConfigError(
                f"country '{code}' is claimed by both '{seen_countries[code]}' and '{region_id}' - "
                "a country must resolve to exactly one region"
            )
        seen_countries[code] = region_id


def build_index(taxonomy: dict) -> GeographyIndex:
    """Validate the region configuration and index it. Raises
    GeographyConfigError on a duplicate id, a country claimed by two regions, an
    unknown ISO code, or a missing global region - the build-failing check Part
    6.1 asks for."""
    regions = taxonomy.get("regions")
    if not isinstance(regions, list) or not regions:
        raise GeographyConfigError("taxonomy.json has no 'regions' array")
    seen_ids, seen_countries = set(), {}
    for entry in regions:
        _validate_region(entry, seen_ids, seen_countries)
    if GLOBAL_REGION not in seen_ids:
        raise GeographyConfigError(
            f"taxonomy.json has no '{GLOBAL_REGION}' region - the classifier's region_override "
            "and every EU-wide signal resolve there, so it cannot be absent"
        )
    for region_id in FALLBACK_CONTINENT_REGIONS:
        if region_id not in seen_ids:
            raise GeographyConfigError(
                f"taxonomy.json has no '{region_id}' region, but it is a continent fallback target"
            )
    return GeographyIndex(regions)


def build_region_block(index: GeographyIndex) -> str:
    """The region vocabulary as prompt text. Member countries are listed so the
    model can sanity-check its own country choice against the grouping, but the
    model is never asked to return a region - it returns countries, and the
    rollup happens here."""
    lines = []
    for entry in index.regions:
        countries = entry.get("countries") or []
        detail = ", ".join(countries) if countries else entry.get("note", "")
        lines.append(f"{entry['id']} - {entry['label']}: {detail}")
    return "\n".join(lines)


@dataclass
class GeographyVerdict:
    """An opportunity space's geography with everything needed to justify it:
    the union, the per-region signal counts the primary was chosen from, and the
    tokens that did not resolve."""
    primary_region: str
    countries: tuple
    regions: tuple
    region_counts: dict
    region_latest: dict
    unresolved: tuple
    tagged_signals: int = 0
    untagged_signals: int = 0
    out_of_window_signals: int = 0
    low_confidence_signals: int = 0

    def as_row(self) -> dict:
        return {
            "primary_region": self.primary_region or None,
            "countries": list(self.countries),
            "regions": list(self.regions),
            "geography_tagged_signals": self.tagged_signals,
            "geography_untagged_signals": self.untagged_signals,
            "geography_out_of_window_signals": self.out_of_window_signals,
            "geography_low_confidence_signals": self.low_confidence_signals,
        }


def aggregate_geography(
    index: GeographyIndex,
    signals: list,
    now: Optional[datetime] = None,
    window_days: int = RECENCY_WINDOW_DAYS,
) -> GeographyVerdict:
    """A space's geography as the union across its qualifying signals.

    Only signals inside the recency window take part, so a stale record's
    country cannot dominate. The primary region is the one carried by the most
    qualifying signals; ties are broken by the most recent contributing signal,
    then by taxonomy order so the result is stable across reruns.

    A space with no geography at all is valid: primary_region is None and the UI
    renders "Global / unspecified". That is deliberately NOT the same as a space
    tagged `global`, which the filter must be able to select on its own.

    A third tie-break - the number of distinct countries backing the region -
    sits between the recency rule and taxonomy order, because signal count and
    recency both degenerate on a space evidenced by a single multi-country
    signal: one CORDIS consortium gives every region it touches count 1 and the
    same date, and without this rule the primary would be decided by whichever
    region happens to be listed first in taxonomy.json. A consortium with four
    Nordic participants and one Belgian is a Nordics topic.

    `signals` are dicts with countries, regions, region_override, signal_date and
    geography_confidence. No other key is read.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)

    countries, regions, unresolved = [], [], []
    region_counts, region_latest, region_countries = {}, {}, {}
    tagged = untagged = out_of_window = low_confidence = 0

    for signal in signals:
        signal_regions = list(signal.get("regions") or [])
        signal_countries = list(signal.get("countries") or [])
        override = signal.get("region_override") or ""
        if override and override not in signal_regions:
            signal_regions.append(override)
        for token in signal.get("unresolved") or ():
            if token not in unresolved:
                unresolved.append(token)
        if not signal_regions and not signal_countries:
            untagged += 1
            continue
        signal_date = parse_date(signal.get("signal_date"))
        if signal_date is None or signal_date < cutoff:
            out_of_window += 1
            continue
        confidence = signal.get("geography_confidence")
        if confidence is not None and float(confidence) < CONFIDENCE_GATE:
            low_confidence += 1
        tagged += 1
        for code in signal_countries:
            if code not in countries:
                countries.append(code)
        for region_id in signal_regions:
            if region_id not in regions:
                regions.append(region_id)
            region_counts[region_id] = region_counts.get(region_id, 0) + 1
            previous = region_latest.get(region_id)
            if previous is None or signal_date > previous:
                region_latest[region_id] = signal_date
            backing = region_countries.setdefault(region_id, set())
            for code in signal_countries:
                if index.region_for(code) == region_id:
                    backing.add(code)

    order = {region_id: position for position, region_id in enumerate(index.ids)}
    regions.sort(key=lambda region_id: order.get(region_id, 99))
    primary = ""
    if region_counts:
        primary = sorted(
            region_counts,
            key=lambda region_id: (
                -region_counts[region_id],
                -(region_latest[region_id].timestamp()),
                -len(region_countries.get(region_id, ())),
                order.get(region_id, 99),
            ),
        )[0]
    return GeographyVerdict(
        primary_region=primary,
        countries=tuple(sorted(countries)),
        regions=tuple(regions),
        region_counts=region_counts,
        region_latest={k: v.date().isoformat() for k, v in region_latest.items()},
        unresolved=tuple(unresolved),
        tagged_signals=tagged,
        untagged_signals=untagged,
        out_of_window_signals=out_of_window,
        low_confidence_signals=low_confidence,
    )


def coverage_report(index: GeographyIndex, verdicts: Iterable[GeographyVerdict]) -> dict:
    """Part 6.5 reporting: spaces per region, the share with no geography at
    all, and every country token that did not resolve to a region."""
    verdicts = list(verdicts)
    total = len(verdicts)
    region_counts = {region_id: 0 for region_id in index.ids}
    primary_counts = {region_id: 0 for region_id in index.ids}
    unresolved_counts: dict = {}
    set_sizes: dict = {}
    no_geography = 0
    for verdict in verdicts:
        for region_id in verdict.regions:
            region_counts[region_id] = region_counts.get(region_id, 0) + 1
        if verdict.primary_region:
            primary_counts[verdict.primary_region] = primary_counts.get(verdict.primary_region, 0) + 1
        else:
            no_geography += 1
        for token in verdict.unresolved:
            unresolved_counts[token] = unresolved_counts.get(token, 0) + 1
        size = len(verdict.regions)
        set_sizes[size] = set_sizes.get(size, 0) + 1
    return {
        "total_spaces": total,
        "regions": region_counts,
        "primary_regions": primary_counts,
        "no_geography": no_geography,
        "no_geography_share": (no_geography / total) if total else 0.0,
        "set_sizes": dict(sorted(set_sizes.items())),
        "unresolved_countries": dict(sorted(unresolved_counts.items())),
        "low_coverage": [
            region_id for region_id in index.ids
            if total and region_counts[region_id] / total < LOW_COVERAGE_SHARE
        ],
        "low_coverage_threshold": LOW_COVERAGE_SHARE,
    }


def format_coverage_report(index: GeographyIndex, report: dict) -> list:
    """The report as log lines, so the pipeline run log carries the same numbers
    the CLI prints."""
    total = report["total_spaces"]
    lines = [f"Geography coverage across {total} opportunity space(s):"]
    for region_id in index.ids:
        count = report["regions"][region_id]
        share = (count / total * 100) if total else 0.0
        lines.append(
            f"  {index.label(region_id)}: {count} ({share:.1f}%) "
            f"- primary on {report['primary_regions'][region_id]}"
        )
    sizes = ", ".join(f"{size} region(s): {count}" for size, count in report["set_sizes"].items())
    lines.append(f"  Region-set sizes - {sizes or 'none'}")
    lines.append(
        f"  No geography at all (primary_region null): {report['no_geography']} "
        f"({report['no_geography_share']:.1%}) - these render as 'Global / unspecified' "
        "and are a distinct filter state from a space tagged global"
    )
    if report["unresolved_countries"]:
        listed = ", ".join(
            f"{token} x{count}" for token, count in report["unresolved_countries"].items()
        )
        lines.append(
            f"  UNRESOLVED country tokens (no region in taxonomy.json, NOT silently assigned): {listed}"
        )
    else:
        lines.append("  Unresolved country tokens: none")
    if report["low_coverage"]:
        labels = ", ".join(index.label(region_id) for region_id in report["low_coverage"])
        lines.append(
            f"  Thin coverage - below {report['low_coverage_threshold']:.0%} of spaces: {labels}"
        )
    return lines


__all__ = [
    "ALPHA2_BY_ALPHA3", "CODE_ALIASES", "CONFIDENCE_GATE", "CONTINENT_BY_ALPHA2",
    "COUNTRY_NAMES", "DETERMINISTIC", "FALLBACK_CONTINENT_REGIONS", "GLOBAL_REGION",
    "INFERRED", "ISO_ALPHA2", "LOW_COVERAGE_SHARE", "RECENCY_WINDOW_DAYS",
    "GeographyConfigError", "GeographyIndex", "GeographyResolution", "GeographyVerdict",
    "aggregate_geography", "build_index", "build_region_block", "coverage_report",
    "format_coverage_report",
]
