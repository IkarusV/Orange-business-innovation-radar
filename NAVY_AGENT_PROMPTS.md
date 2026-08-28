# Every prompt sent to the Navy agent (LLM) in this project

Written 2026-08-28. Every prompt quoted below is copied verbatim from the actual source file at the time of writing (paths given), not paraphrased. There are **6 distinct call sites** across the project where code asks the LLM to do something. Three live in the data pipeline (`Pipelineteamfile/`), three in the app (`radar_v2/`).

All calls go through the same OpenAI-compatible client pattern (`openai.OpenAI(api_key=..., base_url=...)`), reading `NAVY_API_KEY`/`NAVY_BASE_URL`/`NAVY_MODEL` env vars on the pipeline side, or the user's configured Settings (`ai_base_url`/`ai_model`/`ai_api_key`) on the app side.

---

## Pipeline side (`Pipelineteamfile/`)

### 1. Article classification — the main one

- **File**: `Pipelineteamfile/opportunity_classifier/config/prompt_template.txt`, sent by `opportunity_classifier/collector/client.py`'s `classify()`
- **Triggered by**: every full radar run's Stage 4 (`opportunity_classifier/collector/main.py`'s `run()`), classifying each pending article one at a time. Also reused as-is by the backfill scripts (`_backfill_llm_signal_geo.py`, `main.py`'s `backfill_signal_types()`/`backfill_signal_geography()`) and by `evaluate_signal_types.py` (a QA script that runs a golden test set through this same prompt to check for drift — it has no prompt of its own).
- **Model**: `NAVY_MODEL` env var, default `glm-5.1`. `temperature=0.1`, `reasoning={"effort": "none"}`.
- **What it asks for**: exactly one taxonomy match (use case + technology, or null for either), a confidence score under an anchored rubric, one of 6 signal types, two parallel rationale fields (analyst-toned and plain-language), and geography (countries + region).
- **Full template** (`{...}` placeholders are filled per-call — see below):

```
You are classifying an article for the Innovation Radar, which maps articles to a fixed taxonomy of business Use Cases and Technologies, and assigns each article one signal type. This is closed-vocabulary classification: you may only use the exact ids and slugs listed below.

TAXONOMY

{taxonomy_block}

SIGNAL TYPES (choose exactly one slug)

Answer each distinguishing question against the article text alone. The question is the test — not the type name, not the source it came from.

{signal_type_block}

Tie-break priority (highest first): {signal_type_tie_break}
When an article plausibly satisfies more than one distinguishing question, assign the highest-priority type in that order. Concreteness and actor-specificity drive urgency, so the more concrete type wins: an article announcing both a funding programme and a market forecast is a buying_signal, not a market_trend. Assign exactly one type. Never hedge between two — that is what the tie-break is for.

BOUNDARY CHECKS — these two pairs collapse more often than any others. Work through both before answering:
1. competitor_move vs market_trend. Ask who the article is ABOUT. If the named organisation is only quoted, cited as a commentator, or used as an example inside a piece whose subject is a sector-wide question, an advisory, an explainer or a proposal, the answer is market_trend. competitor_move needs the named actor to be the subject AND the announcement to be a concrete thing it did.
2. proof_signal vs competitor_move. Ask whether the thing is already running somewhere identifiable. Delivered, deployed, live, in production, or in use at a named organisation with any stated outcome → proof_signal. Offered, launched, unveiled, demonstrated, planned, or merely claimed → competitor_move.

GEOGRAPHY

Return the countries the article is about as ISO 3166-1 alpha-2 codes. You are not asked for a region — the country codes are rolled up to regions afterwards. For reference only, the regions they roll up to are:

{region_block}

ARTICLE

Vertical: {vertical}
Source: {source_name}
Published: {published_date}
Title: {title}
Summary: {summary}
{client_context_block}
TASK

Return ONLY a single JSON object, with no markdown code fences and no other text:
{"use_case_id": "string or null", "technology_id": "string or null", "confidence": 0.0, "evidence": "short justification grounded in the article text", "signal_type": "one of the exact slugs above", "signal_type_confidence": 0.0, "signal_date": "YYYY-MM-DD or null", "event_date": "YYYY-MM-DD or null", "event_date_precision": "exact|month|quarter|year|none", "signal_type_rationale": "one sentence, max 25 words", "signal_type_plain_summary": "one sentence, max 20 words, plain language", "countries": [], "region_override": "region id or null", "geography_confidence": 0.0}

Rules:
- Only ids from the taxonomy above are valid values for use_case_id and technology_id.
- If no taxonomy entry is a good fit for a dimension, use null for that field. Never force a match, never invent an id.
- Respect the exclusion notes in the definitions when choosing between close entries.
- confidence must follow this rubric — pick the band that matches the evidence, then a specific value within it:
  - 0.90-1.00: Both use_case_id and technology_id are explicitly and unambiguously named in the article text.
  - 0.70-0.89: One dimension is explicit in the text; the other is strongly implied by specific contextual detail.
  - 0.50-0.69: Both dimensions are inferred from general context, not explicitly named — a reasonable reader could plausibly pick a different taxonomy entry instead.
  - Below 0.50: the match is speculative, relying on analogy or a stretch rather than direct evidence.
  - Rule: if either use_case_id or technology_id is null, confidence must not exceed 0.60 — a half-match cannot be reported as highly confident.
- signal_type must be exactly one of the six slugs above, spelled exactly as given. Never invent a seventh type.
- The Vertical and Source lines are context that may help resolve an ambiguity — a defence-procurement feed and a research-institute feed carry different priors. They are a hint only and never override a distinguishing question. An article on a vendor's own blog that reports a customer's measured deployment result is a proof_signal, not a competitor_move, whatever the source is.
- signal_type_confidence is 0.0-1.0: how cleanly one distinguishing question is answered "yes" by the article text. Use a value below 0.5 when two questions are both arguably satisfied and the tie-break, not the text, decided it.
- signal_date is the publication or emission date of the signal itself. Use the Published line above unless the article text states a different emission date for the signal.
- event_date is the date that makes the signal time-bound: compliance deadline, phase-in date, tender close date, contract start. Use null when the article carries no such date — most articles do not. Never put the publication date here.
- event_date_precision describes how exactly event_date is stated: "exact" for a full date, "month" for a named month, "quarter" for a quarter, "year" for a bare year, "none" when event_date is null. A vague "sometime in 2028" is precision "year", not a hard deadline.
- signal_type_rationale is one sentence, max 25 words, quoting or paraphrasing the specific element of the article that triggered the choice.
- signal_type_plain_summary is a second, separate sentence, max 20 words, saying the same underlying fact in plain language for a non-technical business reader: no jargon, no analyst phrasing, no naming the signal type or the taxonomy. State what actually happened (who did what, or what changed), not why it was classified that way - that is what signal_type_rationale is for. Write it as a complete, natural sentence, not a fragment.
- countries is an array of ISO 3166-1 alpha-2 codes, uppercase, for the countries the article is actually about. Rules:
  - Infer from any explicit anchor: a named country, a named city, a named institution or ministry, a company described as headquartered somewhere ("Brussels-based" -> BE, "the German ministry" -> DE, "Singapore's DBS" -> SG).
  - Carry context across sentences. If an earlier sentence names a country and a later one says "the ministry", "the operator" or "the regulator" without repeating it, attribute it to that same country.
  - An article about several countries returns several codes. Do not pick one arbitrarily.
  - The country the article is ABOUT, not the country the publication is from. A US trade title reporting a German plant rollout is DE, not US.
  - If the text carries no geographic anchor at all, return an empty array. An empty array is the correct answer, not a failure — never guess a country to avoid returning nothing.
- region_override is a separate path from countries, for scope that is real but has no single country behind it. Set it to "global" when the article is about EU-wide regulation or a directive with no member state named, a "European" or worldwide market statement, or aggregate statistics spanning many countries — and leave countries empty in that case rather than inventing member states. Use null otherwise. "No geography" and "global scope" are different answers: null with an empty countries array means the text simply has no geography; "global" is a positive claim that the scope is EU-wide or worldwide.
- geography_confidence is 0.0-1.0: how firmly the article text supports the country/scope you returned. Use 0.9+ when a country is named outright, 0.6-0.8 when it follows from a city, institution or carried-over context, below 0.5 when it rests on a weak or indirect hint. Return 0.0 with an empty array and a null override when there is no geographic signal at all.
```

- **Where the placeholders come from**:
  - `{taxonomy_block}` — every use case and technology id + definition, generated from `opportunity_classifier/config/taxonomy.json` by `taxonomy.py`'s `taxonomy_block()`.
  - `{signal_type_block}` / `{signal_type_tie_break}` — the 6 signal types' distinguishing questions, generated from `common/signal_types.py`.
  - `{region_block}` — the region roll-up table, generated from `common/geography.py`.
  - `{vertical}` / `{source_name}` / `{published_date}` / `{title}` / `{summary}` — the article's own fields.
  - `{client_context_block}` — only present when a run was started with `--client-context` (the app's "Company" profile + selected document summaries, built by `radar_v2/services/pipeline_runner.py`'s `company_context_file()`); empty string otherwise. Framed as guidance that "never overrides the taxonomy rules above."
- **Deterministic sources never reach this prompt**: TED, OCDS (UK/Ukraine) and CORDIS get their signal type and geography mechanically from the record itself (`signal_route.py`/`geo_route.py`), at zero LLM cost. Only RSS/GNews articles are actually classified by this prompt for those two fields; every source still gets the taxonomy match (use_case/technology) from this prompt.

### 2. Plain-language rewrite (backfill only)

- **File**: `Pipelineteamfile/opportunity_classifier/collector/client.py`, `PLAIN_SUMMARY_REWRITE_PROMPT`, sent by `rewrite_plain_summary()`
- **Triggered by**: `Pipelineteamfile/_backfill_plain_summary_llm.py` only — a one-off backfill script for articles classified before `signal_type_plain_summary` existed. Not part of the normal 5-stage pipeline; a live/new article gets its plain summary from prompt #1 directly, in the same call as everything else.
- **Model**: same as #1 (`NAVY_MODEL`, `temperature=0.1`).
- **Why it exists separately**: deliberately cheap — takes only the already-produced `signal_type_rationale` text as input, not the article or taxonomy again, so backfilling old rows doesn't cost a full reclassification.
- **Full template**:

```
Explain the following sentence as you would to a colleague with no industry background, in a quick conversation - not a rewrite with fancier synonyms swapped for simpler ones. Use short, everyday words. Avoid formal or analyst phrasing such as 'concrete', 'named actor(s)', 'strategic', 'framework', 'entity', 'stakeholder', 'leverage'. Say plainly who did what, or what changed. Keep exactly the same underlying fact - do not add, remove or invent any detail. One natural sentence, max 20 words. Return ONLY that sentence, no quotes, no markdown, no other text.

Sentence: {rationale}
```

- `{rationale}` = the existing `signal_type_rationale` value for that article.

### 3. Source trust category audit

- **File**: `Pipelineteamfile/source_auditor/config/audit_prompt_template.txt`, sent by `source_auditor/collector/client.py`'s `audit()`
- **Triggered by**: the source auditor tool (`source_auditor/collector/main.py`), run separately from the main radar pipeline — classifies each distinct publisher/source name into a trust category once, which `common/trust.py` then converts into the numeric score `attractiveness.py`'s Source credibility component reads. Not part of `run_radar.py`'s 5 stages.
- **Model**: same env-driven pattern as #1 (`NAVY_MODEL`, `temperature=0.1`).
- **What it asks for**: one closed-vocabulary trust category per source, based on structural facts (named editorial masthead, wire service, peer-reviewed journal, etc.) — explicitly instructed to never judge content quality or guess from the name/topic alone.
- **Full template**:

```
You are classifying a publisher/source for the Innovation Radar pipeline into exactly one fixed category. The category mechanically determines a trust score elsewhere - your only job here is picking the right category, not judging the outlet's quality yourself. This is closed-vocabulary classification: you may only use one of the exact category slugs listed below.

STRICT RULE — READ CAREFULLY: choose the category based on verifiable, structural facts about the publisher (does it have a named editorial masthead? is it a recognized wire service? is it a peer-reviewed journal? is it corporate-owned media where the company is itself the subject of its own coverage?) — not on your opinion of its content quality or topic. If you do not confidently recognize this exact source, or cannot verify which category structurally fits, use "aggregator_unknown". Never guess a higher category. Never infer a category from the source's name or topic alone.

SOURCE
Name: {source_name}
Seen via: {source_type} (context only — not evidence of category)
Example article titles from this source in our data: {example_titles}

CATEGORIES (choose exactly one slug)
{categories_block}

TASK
Return ONLY a single JSON object, with no markdown code fences and no other text:
{"category": "one of the exact slugs above", "evidence": "one or two sentences of verifiable, structural justification", "confidence": 0.0}

Rules:
- category must be exactly one of the listed slugs, spelled exactly as given.
- evidence must state a verifiable structural fact, or say plainly you don't recognize the source (in which case category must be "aggregator_unknown").
- confidence is 0.0-1.0: how confident you are in this category assignment given how well you actually know this exact source. An unrecognized source should score close to 0.0, not a mid-range guess.
```

- `{source_name}` / `{source_type}` / `{example_titles}` (up to 5 real article titles from that source) — per-source. `{categories_block}` — the auto-assignable trust categories, from `common/trust.py`.

---

## App side (`radar_v2/`)

These three use the **user's configured AI provider** from Settings (`ai_base_url`/`ai_model`/`ai_api_key` in `RadarState`), not necessarily the pipeline's `NAVY_API_KEY` — same underlying Navy infrastructure by default (`ai_base_url` defaults to `https://api.navy/v1`), but a different default model (`gpt-5.6-luna` vs. the pipeline's `glm-5.1`) and swappable by the user in Settings.

### 4. Business report — research planning

- **File**: `radar_v2/services/reporting.py`, `create_focused_report()`, first `_json_call()`
- **Triggered by**: clicking "Build business report" on an opportunity's detail page. First of a two-stage LLM flow (plan → search → synthesize).
- **What it asks for**: a JSON `queries` array — search queries to run against the user's configured web search provider (Tavily or SearXNG).
- **System instruction**:
  > You are a senior research planner. Return JSON with a concise queries array. Create varied searches for demand, financial scale/ROI, regulation and risks, implementation proof, and company/competitor/partner fit. Use natural buyer terminology instead of repeating an internal opportunity title.
- **User content** (assembled, not a fixed template):
  ```
  Opportunity: {opportunity JSON}
  Existing evidence: {evidence JSON}
  Company: {active company profile JSON}
  Create at most {max_research_queries} queries.
  ```

### 5. Business report — synthesis

- **File**: `radar_v2/services/reporting.py`, `create_focused_report()`, second `_json_call()`
- **Triggered by**: same report-build flow, after the planned queries have been run through web search and deduplicated.
- **What it asks for**: the full decision-report JSON (executive summary, market signal, financial indicators, company fit, competitor/partner landscape, risks with likelihood/impact/mitigation, a phased roadmap, a recommendation, gaps, and numbered source citations).
- **System instruction**:
  > Create a concise, decision-ready opportunity report using only the supplied evidence and numbered web sources. Return JSON with executive_summary, market_signal, financial_indicators, company_fit, competitor_partner_landscape, risks (array of risk, likelihood, impact, mitigation), roadmap (array of phase, action, success_metric), recommendation, gaps, and source_ids. Keep estimates as ranges with assumptions. Never invent facts.
- **User content** (assembled): the opportunity, existing evidence, the research plan from step 4, and up to 50 deduplicated web search results (source list capped at 70,000 characters).

### 6. Company document summarization (two variants, same shape)

- **File**: `radar_v2/services/knowledge.py`
- **Triggered by**: uploading/processing a document in the Company tab (`process_document()`, one document at a time), or combining ≥2 already-processed documents into one report (`create_combined_report()`).
- **Single-document system instruction** (`process_document`):
  > You are a company knowledge analyst. Summarize only the supplied document; never use facts from another document or outside knowledge. Return JSON with executive_summary, key_facts, financial_signals, strategic_priorities, company_vocabulary, capabilities, risks_and_unknowns, and useful_radar_guidance. Mark uncertainty and keep numbers with their units and periods.
  - User content: `DOCUMENT: {name}\nUSER FOCUS: {instruction or "Provide a balanced company-relevance summary."}\n\nDOCUMENT TEXT:\n{extracted text, capped at 100,000 chars}`
- **Combined-report system instruction** (`create_combined_report`):
  > You are a senior company research analyst. Synthesize the selected company documents into one decision-ready report. Preserve source boundaries, identify repeated themes and contradictions, separate facts from interpretations, and return JSON with report_summary, financial_profile, strategic_priorities, capabilities, company_vocabulary, repeated_themes, contradictions, opportunity_preferences, partnership_preferences, risks_and_unknowns, and radar_guidance.
  - User content: the user's focus instruction, followed by each document's text (each capped at 35,000 chars, source-labeled).
- These summaries feed into prompt #1's `{client_context_block}` for future classification runs, when the user enables "Use this summary as company guidance" and scopes it to "Scoring & fit" or "Everywhere."

---

## What does *not* call the LLM

Worth knowing for completeness — these look like they might, but don't:
- **Discovery** (`radar_v2/state.py`'s `run_discovery`) — pure web search (Tavily/SearXNG), no LLM call at all.
- **Deterministic signal typing/geography** for TED/OCDS/CORDIS — mechanical field extraction (`signal_route.py`/`geo_route.py`), see prompt #1's note above.
- **ML noise filter** (`opportunity_classifier/mlfilter`) — a locally trained scikit-learn/sentence-transformers classifier, not an LLM call.
- **Attractiveness / Orange Fit / horizon scoring** (`radar_v2/services/attractiveness.py`, `horizon.py`) — pure arithmetic over already-stored data, no model call, by explicit design (see that module's own docstring).
- **Explanation fields** ("why hot now" / "why this matters" / "recommended move", `radar_v2/services/explanations.py`) — composed deterministically from typed clauses, no model call at render time, by explicit design.
