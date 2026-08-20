from __future__ import annotations

import math
import re
from collections.abc import Callable
from urllib.parse import urlsplit

from radar.ai import APIBudgetError, AIClient
from radar.company import company_context
from radar.config import load_json
from radar.db import active_company, add_evidence, add_run_event, connect, knowledge_settings, rows, save_analysis_candidate, update_analysis_candidate, upsert_opportunity, utcnow
from radar.intelligence import research_prompt_context, source_metadata, taxonomy_prompt_context
from radar.library import library_context
from radar.ingestion import ingest_enabled_sources
from radar.scoring import horizon_from_signal, horizon_rationale, score_opportunity

SIGNALS = {"regulation", "buying_signal", "market_trend", "market_move", "technology_maturity", "proof_signal"}
FACTOR_KEYS = {"market_signal", "source_diversity", "evidence_quality", "momentum", "strategic_relevance"}
RTW_KEYS = {"offering_fit", "customer_overlap", "references", "partner_readiness"}
ProgressCallback = Callable[[dict], None]


def slugify(*parts: str) -> str:
    return "-".join(filter(None, (re.sub(r"[^a-z0-9]+", "-", str(part).lower()).strip("-") for part in parts)))[:180]


def _bounded_factors(value: dict, keys: set[str]) -> dict:
    return {key: max(0, min(10, float((value or {}).get(key, 0)))) for key in keys}


def _emit(callback: ProgressCallback | None, run_id: int, stage: str, message: str, current: int | None = None, total: int | None = None) -> None:
    add_run_event(run_id, stage, message, current, total)
    if callback:
        callback({"stage": stage, "message": message, "current": current, "total": total})


def pipeline_preflight(maximum: int, batch_size: int, retry_limit: int = 2) -> dict:
    pending = rows("SELECT COUNT(*) count FROM articles WHERE processed=0 AND COALESCE(attempt_count,0) < ?", (retry_limit,))[0]["count"]
    selected = min(pending, maximum)
    return {
        "pending": pending,
        "selected": selected,
        "batch_size": batch_size,
        "estimated_requests": math.ceil(selected / batch_size) if selected else 0,
        "retry_limit": retry_limit,
    }


def _validate_result(result: dict) -> dict:
    result["triage_classification"] = "RELEVANT" if result.get("is_relevant") else "IRRELEVANT"
    result["triage_confidence"] = str(result.get("triage_confidence", "MEDIUM")).upper()
    if result["triage_confidence"] not in {"HIGH", "MEDIUM", "LOW"}:
        result["triage_confidence"] = "MEDIUM"
    if not result.get("is_relevant"):
        return result
    required = ["vertical", "use_case", "technology", "claim", "signal_type"]
    if any(not str(result.get(key, "")).strip() for key in required):
        raise ValueError("AI result is missing a required opportunity field.")
    if result["signal_type"] not in SIGNALS:
        raise ValueError(f"Unsupported signal type: {result['signal_type']}")
    result["attractiveness_factors"] = _bounded_factors(result.get("attractiveness_factors"), FACTOR_KEYS)
    result["right_to_win_factors"] = _bounded_factors(result.get("right_to_win_factors"), RTW_KEYS)
    urgency = max(0, min(10, int(result.get("urgency", 0))))
    result["urgency"] = urgency
    result["horizon"] = horizon_from_signal(result["signal_type"], urgency)
    result["horizon_rationale"] = horizon_rationale(result["signal_type"], urgency)
    return result


def _save_live_triage(article: dict, result: dict, client: AIClient) -> None:
    with connect() as connection:
        connection.execute(
            """INSERT OR REPLACE INTO triage_records(article_guid,article_link,title,source,classification,triage_confidence,signal_type,vertical_id,use_case_id,technology_id,rationale,named_,actor_role,prompt_version,model,classification_method,research_origin,review_status,processed_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                article["guid"], article["url"], article["title"], article["source_name"], result["triage_classification"], result["triage_confidence"],
                result.get("signal_type", ""), result.get("vertical_id", ""), result.get("use_case_id", ""), result.get("technology_id", ""),
                result.get("triage_rationale", result.get("claim", "No evidence value for the active radar scope.")),
                ", ".join(result.get("named_", [])) if isinstance(result.get("named_"), list) else str(result.get("named_", "")),
                result.get("actor_role", ""), load_json("config/prompts.json")["extractor"]["version"], client.model,
                "model-assisted pipeline triage", "radar pipeline", "pending_review", utcnow(),
            ),
        )


def analyze_batch(articles: list[dict], client: AIClient) -> dict[int, dict]:
    prompt = load_json("config/prompts.json")["extractor"]["system"]
    article_blocks = []
    for article in articles:
        metadata = source_metadata(article["source_name"])
        article_blocks.append(
            f"ARTICLE_ID: {article['id']}\nSource: {article['source_name']}\n"
            f"Research source metadata: category={metadata.get('source_category', 'unknown')}; "
            f"quality_default={metadata.get('quality_default', 'unknown')}; "
            f"independence_group={metadata.get('independence_group', 'unknown')}\n"
            f"Published: {article.get('published_at') or 'unknown'}\nURL: {article['url']}\n"
            f"Title: {article['title']}\nContent: {article.get('content', '')[:3500]}"
        )
    compact_articles = "\n\n".join(article_blocks)
    limits = knowledge_settings()
    company_name = active_company().get("name", "")
    stage_budget = max(200, limits["max_context_chars"] // 5)
    general_context = library_context(company_name, "all", limits["max_context_documents"], stage_budget)
    stage_parts = [f"\nGENERAL COMPANY GUIDANCE:\n{general_context}"] if general_context else []
    for stage in ("collection", "opportunity_naming", "scoring", "narrative"):
        context = library_context(company_name, stage, limits["max_context_documents"], stage_budget, include_all=False)
        if context:
            stage_parts.append(f"\nCONTEXT FOR {stage.upper()}:\n{context}")
    stage_contexts = "\n".join(stage_parts)
    instruction = f"""COMPANY AND PARTNER CONTEXT:
{company_context(2500, "unused", 0)}
{stage_contexts}
{research_prompt_context()}

{taxonomy_prompt_context()}

Analyze every external article below independently. Return one JSON object with a `results` array containing exactly one result per ARTICLE_ID. Each result needs:
article_id, is_relevant, vertical, use_case, technology, geography, orange_domain, persona,
signal_type, claim, why_hot_now, why_it_matters, next_action, urgency (0-10),
attractiveness_factors with market_signal, source_diversity, evidence_quality, momentum, strategic_relevance,
right_to_win_factors with offering_fit, customer_overlap, references, partner_readiness,
and score_rationales. For irrelevant articles, article_id and is_relevant are sufficient.
Opportunities may be direct, partner-led, or dependent on external capability. Never mix evidence between articles.

{compact_articles}"""
    payload = client.generate_json(prompt, instruction)
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("Batch response is missing a results array.")
    allowed_ids = {article["id"] for article in articles}
    mapped = {}
    for raw in results:
        article_id = int(raw.get("article_id", -1))
        if article_id in allowed_ids and article_id not in mapped:
            mapped[article_id] = raw
    return mapped


def _store_result(article: dict, result: dict) -> tuple[str, int | None]:
    if not result.get("is_relevant"):
        return "ignored", None
    slug = slugify(result["vertical"], result["use_case"], result["technology"])
    existing = rows("SELECT source_domain,quality FROM evidence e JOIN opportunities o ON o.id=e.opportunity_id WHERE o.slug=?", (slug,))
    domains = {item["source_domain"] for item in existing if item["source_domain"]}
    domains.add(urlsplit(article["url"]).netloc.lower())
    score = score_opportunity(result["attractiveness_factors"], result["right_to_win_factors"], len(existing) + 1, len(domains))
    opportunity_id = upsert_opportunity({
        "slug": slug, "title": f"{result['vertical']} x {result['use_case']} x {result['technology']}",
        "vertical": result["vertical"], "use_case": result["use_case"], "technology": result["technology"],
        "geography": result.get("geography", "Global"), "orange_domain": result.get("orange_domain", "Other"), "persona": result.get("persona", "Strategy"),
        "signal_type": result["signal_type"], "horizon": result["horizon"], "why_hot_now": result.get("why_hot_now", result["claim"]),
        "why_it_matters": result.get("why_it_matters", "Requires company fit validation."), "next_action": result.get("next_action", "Validate with a second independent source."),
        "attractiveness": score.attractiveness, "right_to_win": score.right_to_win, "confidence": score.confidence, "status": score.status,
        "score_rationale": score.rationale, "factors_json": {"attractiveness": result["attractiveness_factors"], "right_to_win": result["right_to_win_factors"], "rationales": result.get("score_rationales", {}), "classification": {"urgency": result["urgency"], "signal_type": result["signal_type"], "horizon_rule": result["horizon_rationale"], "horizon_assigned_by": "Python"}},
    })
    metadata = source_metadata(article["source_name"])
    add_evidence(opportunity_id, {"article_id": article["id"], "source_name": article["source_name"], "source_url": article["url"], "source_domain": urlsplit(article["url"]).netloc.lower(), "published_at": article["published_at"], "signal_type": result["signal_type"], "claim": result["claim"], "quality": result["attractiveness_factors"]["evidence_quality"], "source_category": metadata.get("source_category"), "independence_group": metadata.get("independence_group"), "research_origin": "radar_pipeline using Alec source metadata", "review_status": "pending_review"})
    return "accepted", opportunity_id


def process_pending(client: AIClient, maximum: int, batch_size: int, retry_limit: int, run_id: int, callback: ProgressCallback | None = None) -> dict:
    pending = rows("""SELECT a.*,s.name source_name,s.domain source_domain FROM articles a JOIN sources s ON s.id=a.source_id
        WHERE a.processed=0 AND COALESCE(a.attempt_count,0) < ? ORDER BY COALESCE(a.published_at,a.fetched_at) DESC LIMIT ?""", (retry_limit, maximum))
    accepted = ignored = failed = completed = 0
    total_batches = math.ceil(len(pending) / batch_size) if pending else 0
    for batch_number, start in enumerate(range(0, len(pending), batch_size), 1):
        batch = pending[start:start + batch_size]
        _emit(callback, run_id, "ai_analysis", f"AI batch {batch_number}/{total_batches}: analyzing {len(batch)} articles (HTTP request {client.request_count + 1}/{client.max_requests}).", batch_number - 1, total_batches)
        try:
            results = analyze_batch(batch, client)
            for article in batch:
                candidate_id = None
                try:
                    if article["id"] not in results:
                        raise ValueError("Model omitted this article from the batch response.")
                    raw_result = results[article["id"]]
                    candidate_id = save_analysis_candidate(run_id, article["id"], "captured", raw_result)
                    result = _validate_result(raw_result)
                    _save_live_triage(article, result, client)
                    outcome, opportunity_id = _store_result(article, result)
                    accepted += outcome == "accepted"
                    ignored += outcome == "ignored"
                    completed += 1
                    update_analysis_candidate(candidate_id, "promoted" if outcome == "accepted" else "irrelevant", opportunity_id=opportunity_id)
                    with connect() as connection:
                        connection.execute("UPDATE articles SET processed=1,attempt_count=attempt_count+1,last_error=NULL,last_attempt_at=? WHERE id=?", (utcnow(), article["id"]))
                except Exception as error:
                    failed += 1
                    if candidate_id is not None:
                        update_analysis_candidate(candidate_id, "validation_failed", str(error))
                    else:
                        save_analysis_candidate(run_id, article["id"], "missing_from_response", error=str(error))
                    with connect() as connection:
                        connection.execute("UPDATE articles SET attempt_count=attempt_count+1,last_error=?,last_attempt_at=? WHERE id=?", (str(error)[:1000], utcnow(), article["id"]))
        except APIBudgetError:
            _emit(callback, run_id, "budget", f"Stopped at the hard request limit of {client.max_requests}.", client.request_count, client.max_requests)
            break
        except Exception as error:
            failed += len(batch)
            for article in batch:
                save_analysis_candidate(run_id, article["id"], "request_failed", error=str(error))
            with connect() as connection:
                for article in batch:
                    connection.execute("UPDATE articles SET attempt_count=attempt_count+1,last_error=?,last_attempt_at=? WHERE id=?", (str(error)[:1000], utcnow(), article["id"]))
        _emit(callback, run_id, "ai_analysis", f"Batch {batch_number}/{total_batches} complete. Accepted {accepted}, ignored {ignored}, failed {failed}.", batch_number, total_batches)
    return {"selected": len(pending), "processed": completed, "accepted": accepted, "ignored": ignored, "failed": failed, "api_requests": client.request_count}


def refresh(client: AIClient | None = None, maximum: int = 20, batch_size: int = 5, retry_limit: int = 2, callback: ProgressCallback | None = None) -> dict:
    with connect() as connection:
        run_id = connection.execute("INSERT INTO runs(started_at,status) VALUES(?,?)", (utcnow(), "running")).lastrowid
    try:
        _emit(callback, run_id, "collection", "Step 1/4: collecting enabled RSS feeds.")
        ingestion = ingest_enabled_sources()
        _emit(callback, run_id, "collection", f"Step 1/4 complete: {ingestion['added']} new signals, {ingestion['failures']} source failures.")
        if client:
            preflight = pipeline_preflight(maximum, batch_size, retry_limit)
            _emit(callback, run_id, "selection", f"Step 2/4: selected {preflight['selected']} of {preflight['pending']} eligible pending articles; estimated {preflight['estimated_requests']} batch requests.")
            analysis = process_pending(client, maximum, batch_size, retry_limit, run_id, callback)
        else:
            analysis = {"selected": 0, "processed": 0, "accepted": 0, "ignored": 0, "failed": 0, "api_requests": 0}
        _emit(callback, run_id, "scoring", "Step 3/4 complete: accepted evidence was grouped, scored, and saved.")
        notes = "Ingestion only: configure an API key to analyze." if not client else f"Completed with {analysis['api_requests']} API request(s)."
        with connect() as connection:
            connection.execute("UPDATE runs SET finished_at=?,status=?,fetched_count=?,processed_count=?,notes=? WHERE id=?", (utcnow(), "completed", ingestion["added"], analysis["processed"], notes, run_id))
        _emit(callback, run_id, "complete", "Step 4/4: pipeline finished. Dashboard data is persisted.")
        return {**ingestion, **analysis, "run_id": run_id, "notes": notes}
    except Exception as error:
        with connect() as connection:
            connection.execute("UPDATE runs SET finished_at=?,status='failed',notes=? WHERE id=?", (utcnow(), str(error)[:1000], run_id))
        _emit(callback, run_id, "failed", f"Pipeline failed: {error}")
        raise
