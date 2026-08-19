from __future__ import annotations

import csv
import math
from pathlib import Path

from radar.config import ROOT
from radar.db import connect, rows

ALEC_ROOT = ROOT / "Aorangeresearch" / "Alec2" / "proto_analysis"
RESEARCH_ORIGIN = "Alec human research prototype"

TAXONOMY_FILES = {
    "vertical": ("verticals.csv", "vertical_id", "vertical_name", "", "notes"),
    "use_case": ("use_cases.csv", "use_case_id", "use_case_name", "vertical_id", "description"),
    "technology": ("technologies.csv", "technology_id", "technology_name", "", "description"),
    "signal_type": ("signal_types.csv", "signal_type_id", "signal_type_name", "", "description"),
}


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def sync_alec_research() -> dict:
    counts = {"taxonomy": 0, "aliases": 0, "sources": 0, "triage": 0, "coverage": 0}
    with connect() as connection:
        for taxonomy_type, (filename, id_field, name_field, parent_field, description_field) in TAXONOMY_FILES.items():
            for item in _read_csv(ALEC_ROOT / "taxonomy" / filename):
                connection.execute(
                    """INSERT INTO taxonomy_terms(taxonomy_type,canonical_id,display_name,parent_id,description,status,research_origin)
                    VALUES(?,?,?,?,?,?,?) ON CONFLICT(taxonomy_type,canonical_id) DO UPDATE SET display_name=excluded.display_name,parent_id=excluded.parent_id,description=excluded.description,status=excluded.status,research_origin=excluded.research_origin""",
                    (taxonomy_type, item[id_field], item[name_field], item.get(parent_field, "") if parent_field else "", item.get(description_field, ""), item.get("status", "approved"), RESEARCH_ORIGIN),
                )
                counts["taxonomy"] += 1
        for item in _read_csv(ALEC_ROOT / "taxonomy" / "synonym_map.csv"):
            connection.execute(
                """INSERT INTO taxonomy_aliases(taxonomy_type,canonical_id,alias,status,research_origin) VALUES(?,?,?,?,?)
                ON CONFLICT(taxonomy_type,alias) DO UPDATE SET canonical_id=excluded.canonical_id,status=excluded.status,research_origin=excluded.research_origin""",
                (item["canonical_type"], item["canonical_id"], item["alias"], item.get("status", "approved"), RESEARCH_ORIGIN),
            )
            counts["aliases"] += 1
        for item in _read_csv(ALEC_ROOT / "source_registry.csv"):
            connection.execute(
                """INSERT INTO intelligence_sources(name,feed_url,source_category,quality_default,independence_group,domain,vertical_scope,expected_signal_types,language,active,research_origin)
                VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET feed_url=excluded.feed_url,source_category=excluded.source_category,quality_default=excluded.quality_default,independence_group=excluded.independence_group,domain=excluded.domain,vertical_scope=excluded.vertical_scope,expected_signal_types=excluded.expected_signal_types,language=excluded.language,active=excluded.active,research_origin=excluded.research_origin""",
                (item["source"], item["feed_url"], item["source_category"], int(item["source_quality_default"]), item["independence_group"], item["domain"], item["vertical_scope"], item["signal_types"], item["language"], int(item["active"].lower() == "true"), RESEARCH_ORIGIN),
            )
            counts["sources"] += 1
        for item in _read_csv(ALEC_ROOT / "market_intelligence_data" / "triage_results.csv"):
            method = "human-directed model-assisted pilot" if item.get("model") else "human research"
            connection.execute(
                """INSERT OR IGNORE INTO triage_records(article_guid,article_link,title,source,classification,triage_confidence,signal_type,vertical_id,use_case_id,technology_id,rationale,named_organizations,actor_role,prompt_version,model,classification_method,research_origin,review_status,processed_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (item["article_guid"], item["article_link"], item["title"], item["source"], item["classification"], item["triage_confidence"], normalize_signal(item.get("signal_type", "")), item.get("vertical_id", ""), item.get("use_case_id", ""), item.get("technology_id", ""), item["rationale"], "", "", item.get("prompt_version", ""), item.get("model", ""), method, RESEARCH_ORIGIN, item.get("review_status", "pending_review"), item.get("processed_at", "")),
            )
            counts["triage"] += 1
        for item in _read_csv(ALEC_ROOT / "market_intelligence_data" / "manufacturing_coverage_matrix.csv"):
            connection.execute(
                """INSERT INTO coverage_gaps(vertical_id,signal_type,available_sources,independence_groups,raw_articles,status,gap,next_action,last_reviewed,research_origin)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(vertical_id,signal_type) DO UPDATE SET available_sources=excluded.available_sources,independence_groups=excluded.independence_groups,raw_articles=excluded.raw_articles,status=excluded.status,gap=excluded.gap,next_action=excluded.next_action,last_reviewed=excluded.last_reviewed,research_origin=excluded.research_origin""",
                (item["vertical"], normalize_signal(item["signal_type"]), int(item["available_sources"]), int(item["independence_groups"]), int(item["raw_articles"]), item["status"], item["gap"], item["next_action"], item["last_reviewed"], RESEARCH_ORIGIN),
            )
            counts["coverage"] += 1
    return counts


def normalize_signal(value: str) -> str:
    return {"buying": "buying_signal", "proof": "proof_signal", "maturity": "technology_maturity"}.get(value, value)


def taxonomy_prompt_context() -> str:
    terms = rows("SELECT taxonomy_type,canonical_id,display_name,parent_id FROM taxonomy_terms WHERE status='approved' ORDER BY taxonomy_type,canonical_id")
    aliases = rows("SELECT taxonomy_type,canonical_id,alias FROM taxonomy_aliases WHERE status='approved' ORDER BY taxonomy_type,canonical_id")
    term_lines = [f"{item['taxonomy_type']}:{item['canonical_id']}={item['display_name']}" + (f" (parent {item['parent_id']})" if item['parent_id'] else "") for item in terms]
    alias_lines = [f"{item['alias']} -> {item['taxonomy_type']}:{item['canonical_id']}" for item in aliases]
    return "PROTOTYPE CANONICAL TAXONOMY (prefer these IDs when supported; leave blank rather than guess):\n" + "\n".join(term_lines + alias_lines)


def source_metadata(source_name: str) -> dict:
    result = rows("SELECT * FROM intelligence_sources WHERE name=?", (source_name,))
    return result[0] if result else {}


def evidence_strength(article_count: int, independence_count: int, high_value_count: int, reference_count: int = 20) -> dict:
    volume = min(math.log1p(max(article_count, 0)) / math.log1p(reference_count), 1.0) * 100
    independence = min(max(independence_count, 0) / 5, 1.0) * 100
    quality = (max(high_value_count, 0) / article_count * 100) if article_count else 0
    score = round(0.40 * volume + 0.35 * independence + 0.25 * quality, 1)
    return {"score": score, "volume": round(volume, 1), "independence": round(independence, 1), "signal_quality": round(quality, 1)}


def opportunity_evidence_strength(opportunity_id: int) -> dict:
    evidence = rows("SELECT signal_type,COALESCE(independence_group,source_domain) independence FROM evidence WHERE opportunity_id=?", (opportunity_id,))
    strong = {"regulation", "buying_signal", "proof_signal"}
    return evidence_strength(len(evidence), len({item["independence"] for item in evidence if item["independence"]}), sum(item["signal_type"] in strong for item in evidence))
