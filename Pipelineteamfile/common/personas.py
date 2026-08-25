"""Target personas: the closed eight-entry buyer vocabulary and the
deterministic derivation of a space's weighted persona set.

Same shape as common/business_domains.py, one level over: a persona is not a
membership flag but a weight, because this dimension has to answer two
questions - "show me topics for a CIO" (filter) and "show me the three topics
worth bringing to this CIO" (rank). A boolean table can only answer the first.

Weights are three discrete tiers (1.0 / 0.6 / 0.3) rather than free floats:
hand-authored continuous weights drift inconsistent past a handful of rows,
while tiers stay comparable across the whole table. An absent pair is 0.0 and
is never written as an explicit zero row.

Derivation is pure and reads three tables from
opportunity_classifier/config/taxonomy.json:
    use_cases[].personas       - the primary table
    business_domains[].personas - an overlay catching relevance the use case
                                  table misses (any cybersecurity topic should
                                  register some CISO relevance)
    persona_suppressions        - persona x vertical pairs that are structurally
                                  implausible whatever the tables produce

The two contributions combine with max(), not sum: summing would let two
peripheral signals outrank a genuine primary match and push totals past 1.0,
which breaks the ranking multiplier below.

No LLM call and no classification stage is involved, so the whole corpus is
recomputable from configuration at any time.
"""
from dataclasses import dataclass
from typing import Iterable, Optional

PRIMARY_WEIGHT = 1.0
SECONDARY_WEIGHT = 0.6
PERIPHERAL_WEIGHT = 0.3
WEIGHT_TIERS = {
    "primary": PRIMARY_WEIGHT,
    "secondary": SECONDARY_WEIGHT,
    "peripheral": PERIPHERAL_WEIGHT,
}
VALID_WEIGHTS = (PRIMARY_WEIGHT, SECONDARY_WEIGHT, PERIPHERAL_WEIGHT)

# Any non-suppressed match. Role modes may raise this (Sales defaults to 0.6).
DEFAULT_WEIGHT_THRESHOLD = PERIPHERAL_WEIGHT

# A persona holding less than this share of the corpus is a coverage problem in
# the mapping tables, not an acceptable outcome.
LOW_COVERAGE_SHARE = 0.05

# persona_adjusted_score = base * (FLOOR + SCALE * weight). Named rather than
# inlined because both will need calibration once live ranking output exists.
# The floor is what keeps this a dampened multiplier and not a hidden filter:
# an unmatched space is deprioritised to half score, never removed.
PERSONA_SCORE_FLOOR = 0.5
PERSONA_SCORE_SCALE = 0.5

USE_CASE = "use_case"
DOMAIN = "domain"
BOTH = "both"


class PersonaConfigError(ValueError):
    """Raised when taxonomy.json carries an unusable persona configuration.
    Deliberately fatal: an unknown slug or an unmapped use case would silently
    produce spaces that no persona filter can ever return."""


@dataclass(frozen=True)
class PersonaWeight:
    """One persona's derived relevance to one space, keeping both raw
    contributions so the UI can show why the topic is flagged for this buyer."""
    persona: str
    weight: float
    source: str
    use_case_weight: float
    domain_weight: float
    suppressed: bool = False


@dataclass(frozen=True)
class PersonaResolution:
    """One space's weighted persona set. Suppressed pairs are kept separately
    rather than dropped, so a suppression rule that fires stays auditable
    instead of looking like an absent mapping."""
    weights: tuple
    suppressed: tuple

    def weight_of(self, persona_id: str) -> float:
        for entry in self.weights:
            if entry.persona == persona_id:
                return entry.weight
        return 0.0

    def source_of(self, persona_id: str) -> str:
        for entry in self.weights:
            if entry.persona == persona_id:
                return entry.source
        return ""

    def personas_at(self, threshold: float = DEFAULT_WEIGHT_THRESHOLD) -> tuple:
        return tuple(entry.persona for entry in self.weights if entry.weight >= threshold)


def adjusted_score(base_score: float, weight: float) -> float:
    """Dampened persona multiplier: 1.0x at primary, 0.8x at secondary, 0.65x at
    peripheral, 0.5x at absent or suppressed. Persona reorders good topics; it
    never lets a weak topic outrank a strong one on persona fit alone."""
    return base_score * (PERSONA_SCORE_FLOOR + PERSONA_SCORE_SCALE * weight)


class PersonaIndex:
    """Validated view over taxonomy.json's persona configuration."""

    def __init__(self, personas: list, by_use_case: dict, by_domain: dict, suppressions: list):
        self.personas = personas
        self.ids = [entry["id"] for entry in personas]
        self.labels = {entry["id"]: entry["label"] for entry in personas}
        self.by_use_case = by_use_case
        self.by_domain = by_domain
        self.suppressions = suppressions
        self._suppressed_pairs = {
            (rule["persona"], rule["vertical"]) for rule in suppressions
        }
        self._order = {persona_id: position for position, persona_id in enumerate(self.ids)}

    def label(self, persona_id: str) -> str:
        return self.labels.get(persona_id, persona_id)

    def options(self) -> list:
        """Vocabulary in taxonomy order - what a persona picker renders."""
        return [{"id": entry["id"], "label": entry["label"]} for entry in self.personas]

    def is_suppressed(self, persona_id: str, vertical: Optional[str]) -> bool:
        return (persona_id, vertical or "") in self._suppressed_pairs

    def suppression_reason(self, persona_id: str, vertical: Optional[str]) -> str:
        for rule in self.suppressions:
            if rule["persona"] == persona_id and rule["vertical"] == (vertical or ""):
                return rule["reason"]
        return ""

    def resolve(
        self,
        use_case_id: Optional[str],
        primary_domain: Optional[str],
        vertical: Optional[str] = None,
    ) -> PersonaResolution:
        """Combine the use case table with the primary domain overlay by max(),
        then apply suppression. Only the primary domain contributes: the full
        domain set would let a secondary domain drag in a buyer the topic does
        not actually belong to."""
        use_case_weights = self.by_use_case.get(use_case_id or "")
        if use_case_weights is None:
            raise PersonaConfigError(
                f"use case '{use_case_id}' has no persona weights - every opportunity space "
                "must resolve against the persona table, so this is a data or mapping error"
            )
        domain_weights = self.by_domain.get(primary_domain or "", {})

        kept, suppressed = [], []
        for persona_id in sorted(
            set(use_case_weights) | set(domain_weights), key=lambda pid: self._order.get(pid, 99)
        ):
            from_use_case = use_case_weights.get(persona_id, 0.0)
            from_domain = domain_weights.get(persona_id, 0.0)
            combined = max(from_use_case, from_domain)
            if from_use_case and from_domain:
                source = BOTH
            elif from_use_case:
                source = USE_CASE
            else:
                source = DOMAIN
            entry = PersonaWeight(
                persona=persona_id,
                weight=combined,
                source=source,
                use_case_weight=from_use_case,
                domain_weight=from_domain,
            )
            if self.is_suppressed(persona_id, vertical):
                suppressed.append(PersonaWeight(
                    persona=persona_id, weight=0.0, source=entry.source,
                    use_case_weight=from_use_case, domain_weight=from_domain, suppressed=True,
                ))
            else:
                kept.append(entry)
        kept.sort(key=lambda item: (-item.weight, self._order.get(item.persona, 99)))
        return PersonaResolution(weights=tuple(kept), suppressed=tuple(suppressed))


def _entry_weights(entry: dict, kind: str, valid: set) -> dict:
    raw = entry.get("personas")
    if raw is None:
        raise PersonaConfigError(f"{kind} '{entry['id']}' has no 'personas' array")
    if not isinstance(raw, list) or not raw:
        raise PersonaConfigError(f"{kind} '{entry['id']}' has an empty or malformed 'personas' array")
    weights = {}
    for item in raw:
        persona_id = item.get("persona")
        if persona_id not in valid:
            raise PersonaConfigError(
                f"{kind} '{entry['id']}' references unknown persona: {persona_id!r}"
            )
        if persona_id in weights:
            raise PersonaConfigError(f"{kind} '{entry['id']}' repeats persona '{persona_id}'")
        weight = item.get("weight")
        if weight not in VALID_WEIGHTS:
            raise PersonaConfigError(
                f"{kind} '{entry['id']}' gives persona '{persona_id}' weight {weight!r} - "
                f"only the discrete tiers {VALID_WEIGHTS} are allowed"
            )
        weights[persona_id] = float(weight)
    return weights


def _suppressions(taxonomy: dict, valid: set) -> list:
    raw = taxonomy.get("persona_suppressions", [])
    if not isinstance(raw, list):
        raise PersonaConfigError("'persona_suppressions' must be a list")
    rules = []
    for item in raw:
        persona_id = item.get("persona")
        vertical = item.get("vertical")
        if persona_id not in valid:
            raise PersonaConfigError(f"suppression references unknown persona: {persona_id!r}")
        if not vertical:
            raise PersonaConfigError(f"suppression for persona '{persona_id}' has no vertical")
        rules.append({
            "persona": persona_id, "vertical": vertical, "reason": item.get("reason", ""),
        })
    return rules


def build_index(taxonomy: dict) -> PersonaIndex:
    """Validate the persona configuration and index it. Raises
    PersonaConfigError on an unknown slug, a duplicate, an off-tier weight or a
    use case with no mapping - the build-failing check Part 9.1 asks for."""
    personas = taxonomy.get("personas")
    if not isinstance(personas, list) or not personas:
        raise PersonaConfigError("taxonomy.json has no 'personas' array")
    ids = [entry["id"] for entry in personas]
    if len(set(ids)) != len(ids):
        raise PersonaConfigError(f"duplicate persona ids: {ids}")
    valid = set(ids)
    by_use_case = {
        entry["id"]: _entry_weights(entry, "use case", valid)
        for entry in taxonomy["use_cases"]
    }
    by_domain = {
        entry["id"]: _entry_weights(entry, "business domain", valid)
        for entry in taxonomy["business_domains"]
    }
    return PersonaIndex(personas, by_use_case, by_domain, _suppressions(taxonomy, valid))


def coverage_report(index: PersonaIndex, resolutions: Iterable[PersonaResolution]) -> dict:
    """Part 9.2 and 9.3: per-persona counts at the default threshold, the tier
    distribution behind them, which personas fall under the coverage floor, and
    how often each suppression rule actually fired."""
    resolutions = list(resolutions)
    total = len(resolutions)
    counts = {persona_id: 0 for persona_id in index.ids}
    primary_counts = {persona_id: 0 for persona_id in index.ids}
    source_counts = {USE_CASE: 0, DOMAIN: 0, BOTH: 0}
    suppression_counts = {}
    set_sizes: dict = {}
    for resolution in resolutions:
        matched = 0
        for entry in resolution.weights:
            if entry.weight >= DEFAULT_WEIGHT_THRESHOLD:
                counts[entry.persona] += 1
                source_counts[entry.source] += 1
                matched += 1
            if entry.weight >= PRIMARY_WEIGHT:
                primary_counts[entry.persona] += 1
        for entry in resolution.suppressed:
            key = entry.persona
            suppression_counts[key] = suppression_counts.get(key, 0) + 1
        set_sizes[matched] = set_sizes.get(matched, 0) + 1
    low_coverage = [
        persona_id for persona_id in index.ids
        if total and counts[persona_id] / total < LOW_COVERAGE_SHARE
    ]
    return {
        "total_spaces": total,
        "threshold": DEFAULT_WEIGHT_THRESHOLD,
        "counts": counts,
        "primary_counts": primary_counts,
        "sources": source_counts,
        "suppressions_fired": suppression_counts,
        "suppressed_total": sum(suppression_counts.values()),
        "set_sizes": dict(sorted(set_sizes.items())),
        "low_coverage": low_coverage,
        "low_coverage_threshold": LOW_COVERAGE_SHARE,
    }


def format_coverage_report(index: PersonaIndex, report: dict) -> list:
    """The report as log lines, so the pipeline run log carries the same
    numbers the CLI prints."""
    total = report["total_spaces"]
    lines = [
        f"Target persona coverage across {total} opportunity space(s) "
        f"at weight >= {report['threshold']}:"
    ]
    for persona_id in index.ids:
        count = report["counts"][persona_id]
        share = (count / total * 100) if total else 0.0
        lines.append(
            f"  {index.label(persona_id)}: {count} ({share:.1f}%) "
            f"- primary on {report['primary_counts'][persona_id]}"
        )
    sizes = ", ".join(f"{size} persona(s): {count}" for size, count in report["set_sizes"].items())
    lines.append(f"  Persona-set sizes - {sizes or 'none'}")
    lines.append(
        f"  Weight sources - use case only {report['sources'][USE_CASE]}, "
        f"domain overlay only {report['sources'][DOMAIN]}, both {report['sources'][BOTH]}"
    )
    if report["suppressed_total"]:
        fired = ", ".join(
            f"{index.label(persona_id)} x{count}"
            for persona_id, count in sorted(report["suppressions_fired"].items())
        )
        lines.append(f"  Suppression rules fired {report['suppressed_total']} time(s): {fired}")
    else:
        lines.append("  Suppression rules fired 0 times - the list is currently inert")
    if report["low_coverage"]:
        labels = ", ".join(index.label(persona_id) for persona_id in report["low_coverage"])
        lines.append(
            f"  COVERAGE CONCERN: below {report['low_coverage_threshold']:.0%} of spaces - {labels}"
        )
    return lines


def explain(index: PersonaIndex, resolution: PersonaResolution) -> list:
    """Part 9.4: the full derivation of one space as readable lines - use case
    weight, domain weight, combined, suppression, final weight and source."""
    lines = []
    for entry in resolution.weights:
        lines.append(
            f"    {index.label(entry.persona)}: use_case={entry.use_case_weight:.1f} "
            f"domain={entry.domain_weight:.1f} -> max={entry.weight:.1f} "
            f"[{entry.source}] not suppressed -> final {entry.weight:.1f}"
        )
    for entry in resolution.suppressed:
        combined = max(entry.use_case_weight, entry.domain_weight)
        lines.append(
            f"    {index.label(entry.persona)}: use_case={entry.use_case_weight:.1f} "
            f"domain={entry.domain_weight:.1f} -> max={combined:.1f} "
            f"[{entry.source}] SUPPRESSED -> final 0.0"
        )
    return lines or ["    no persona relevance derived"]


__all__ = [
    "BOTH", "DEFAULT_WEIGHT_THRESHOLD", "DOMAIN", "LOW_COVERAGE_SHARE",
    "PERIPHERAL_WEIGHT", "PERSONA_SCORE_FLOOR", "PERSONA_SCORE_SCALE",
    "PRIMARY_WEIGHT", "SECONDARY_WEIGHT", "USE_CASE", "VALID_WEIGHTS", "WEIGHT_TIERS",
    "PersonaConfigError", "PersonaIndex", "PersonaResolution", "PersonaWeight",
    "adjusted_score", "build_index", "coverage_report", "explain", "format_coverage_report",
]
