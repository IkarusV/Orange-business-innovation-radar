"""Orange business domains: the closed six-entry vocabulary and the
deterministic derivation of a space's domain set from its taxonomy assignment.

Same shape as common/trust.py and common/signal_types.py - the rules live here
as the single source of truth, imported by both the pipeline (which derives and
persists) and the app (which reads and filters).

The vocabulary and both mapping tables live in
opportunity_classifier/config/taxonomy.json, never in code, so a correction is
a config edit plus a backfill rerun rather than a release. This module only
validates that configuration and applies it.

Derivation is pure: a space's domains are the union of its technology's domains
and its use case's domains. The primary is always the first entry of the
technology list, never the use case list, so single-value display stays stable
and unambiguous. No LLM call and no classification stage is involved, which is
what makes the whole corpus recomputable from configuration at any time.
"""
from dataclasses import dataclass
from typing import Iterable, Optional

# A domain holding less than this share of the corpus is a coverage problem in
# the mapping tables or the taxonomy, not an acceptable outcome.
LOW_COVERAGE_SHARE = 0.05

TECHNOLOGY = "technology"
USE_CASE = "use_case"
BOTH = "both"


class DomainConfigError(ValueError):
    """Raised when taxonomy.json carries an unusable domain configuration.
    Deliberately fatal: an unknown slug or an unmapped technology would
    silently produce spaces that no domain filter can ever return."""


@dataclass(frozen=True)
class DomainResolution:
    """One space's derived domains, keeping the two contributions separate so
    the optional use-case table's effect stays measurable after the fact."""
    primary: str
    domains: tuple
    technology_domains: tuple
    use_case_domains: tuple

    def source_of(self, domain_id: str) -> str:
        in_technology = domain_id in self.technology_domains
        in_use_case = domain_id in self.use_case_domains
        if in_technology and in_use_case:
            return BOTH
        return TECHNOLOGY if in_technology else USE_CASE


class DomainIndex:
    """Validated view over taxonomy.json's domain configuration."""

    def __init__(self, domains: list, by_technology: dict, by_use_case: dict):
        self.domains = domains
        self.ids = [entry["id"] for entry in domains]
        self.labels = {entry["id"]: entry["label"] for entry in domains}
        self.by_technology = by_technology
        self.by_use_case = by_use_case

    def label(self, domain_id: str) -> str:
        return self.labels.get(domain_id, domain_id)

    def resolve(self, technology_id: Optional[str], use_case_id: Optional[str]) -> DomainResolution:
        technology_domains = self.by_technology.get(technology_id or "")
        if not technology_domains:
            raise DomainConfigError(
                f"technology '{technology_id}' has no business domains - every opportunity space "
                "must resolve to at least one domain, so this is a data or mapping error"
            )
        use_case_domains = self.by_use_case.get(use_case_id or "", ())
        ordered = list(technology_domains)
        for domain_id in use_case_domains:
            if domain_id not in ordered:
                ordered.append(domain_id)
        return DomainResolution(
            primary=technology_domains[0],
            domains=tuple(ordered),
            technology_domains=tuple(technology_domains),
            use_case_domains=tuple(use_case_domains),
        )


def _entry_domains(entry: dict, kind: str, valid: set, required: bool) -> tuple:
    raw = entry.get("domains")
    if raw is None:
        if required:
            raise DomainConfigError(f"{kind} '{entry['id']}' has no 'domains' array")
        return ()
    if not isinstance(raw, list) or not raw:
        raise DomainConfigError(f"{kind} '{entry['id']}' has an empty or malformed 'domains' array")
    unknown = [slug for slug in raw if slug not in valid]
    if unknown:
        raise DomainConfigError(f"{kind} '{entry['id']}' references unknown business domains: {unknown}")
    if len(set(raw)) != len(raw):
        raise DomainConfigError(f"{kind} '{entry['id']}' repeats a business domain: {raw}")
    return tuple(raw)


def build_index(taxonomy: dict) -> DomainIndex:
    """Validate the domain configuration and index it. Raises DomainConfigError
    on an unknown slug, a duplicate, or a technology with no mapping - the
    build-failing check Part 6 of the spec asks for."""
    domains = taxonomy.get("business_domains")
    if not isinstance(domains, list) or not domains:
        raise DomainConfigError("taxonomy.json has no 'business_domains' array")
    ids = [entry["id"] for entry in domains]
    if len(set(ids)) != len(ids):
        raise DomainConfigError(f"duplicate business domain ids: {ids}")
    valid = set(ids)
    by_technology = {
        entry["id"]: _entry_domains(entry, "technology", valid, required=True)
        for entry in taxonomy["technologies"]
    }
    by_use_case = {
        entry["id"]: _entry_domains(entry, "use case", valid, required=False)
        for entry in taxonomy["use_cases"]
    }
    return DomainIndex(domains, by_technology, {k: v for k, v in by_use_case.items() if v})


def coverage_report(index: DomainIndex, resolutions: Iterable[DomainResolution]) -> dict:
    """Part 6 reporting: per-domain counts under the technology table alone and
    under the union, the distribution of domain-set sizes, and any domain below
    the coverage floor."""
    resolutions = list(resolutions)
    total = len(resolutions)
    technology_counts = {domain_id: 0 for domain_id in index.ids}
    union_counts = {domain_id: 0 for domain_id in index.ids}
    set_sizes: dict = {}
    for resolution in resolutions:
        for domain_id in resolution.technology_domains:
            technology_counts[domain_id] += 1
        for domain_id in resolution.domains:
            union_counts[domain_id] += 1
        size = len(resolution.domains)
        set_sizes[size] = set_sizes.get(size, 0) + 1
    low_coverage = [
        domain_id for domain_id in index.ids
        if total and union_counts[domain_id] / total < LOW_COVERAGE_SHARE
    ]
    return {
        "total_spaces": total,
        "technology_only": technology_counts,
        "union": union_counts,
        "use_case_contribution": {
            domain_id: union_counts[domain_id] - technology_counts[domain_id]
            for domain_id in index.ids
        },
        "set_sizes": dict(sorted(set_sizes.items())),
        "low_coverage": low_coverage,
        "low_coverage_threshold": LOW_COVERAGE_SHARE,
    }


def format_coverage_report(index: DomainIndex, report: dict) -> list:
    """The report as log lines, so the pipeline run log carries the same
    numbers the CLI prints."""
    total = report["total_spaces"]
    lines = [f"Business domain coverage across {total} opportunity space(s):"]
    for domain_id in index.ids:
        union = report["union"][domain_id]
        technology_only = report["technology_only"][domain_id]
        share = (union / total * 100) if total else 0.0
        lines.append(
            f"  {index.label(domain_id)}: {union} ({share:.1f}%) "
            f"- technology table alone {technology_only}, "
            f"use-case table adds {report['use_case_contribution'][domain_id]}"
        )
    sizes = ", ".join(f"{size} domain(s): {count}" for size, count in report["set_sizes"].items())
    lines.append(f"  Domain-set sizes - {sizes or 'none'}")
    if report["low_coverage"]:
        labels = ", ".join(index.label(domain_id) for domain_id in report["low_coverage"])
        lines.append(
            f"  COVERAGE PROBLEM: below {report['low_coverage_threshold']:.0%} of spaces - {labels}"
        )
    return lines


__all__ = [
    "BOTH", "DomainConfigError", "DomainIndex", "DomainResolution",
    "LOW_COVERAGE_SHARE", "TECHNOLOGY", "USE_CASE",
    "build_index", "coverage_report", "format_coverage_report",
]
