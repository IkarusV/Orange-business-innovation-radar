# Attractiveness scoring — implementation summary

## Background

The app previously showed a "Strategic fit" percentage that was actually one of two things depending on data availability: a rarely-populated LLM field, or — in practice, almost always — a raw `article_count / max_count` ratio dressed up as a percentage. It didn't explain itself, which failed the requirements deck's hard rule (slide 16): "the scoring model must explain the number." Full root-cause detail is in `docs/scoring_requirements_gap_analysis_2026-08-25.pdf`.

It's replaced with a 5-component **Attractiveness score** (weights fixed by the deck, slide 17: 30/20/20/15/15) plus a separately-computed **Urgency / time horizon** badge (Now/Next/Later) — two different questions ("how strong is the evidence" vs. "how far away is the thing that makes this matter") that are deliberately kept independent.

All scoring logic lives in `radar_v2/services/attractiveness.py`; it's wired into the opportunity list in `radar_v2/services/team_repository.py`'s `list_opportunities()`.

## The 5 weighted components

### 1. Market signal strength — 30%
*How visible is this opportunity across external sources, weighted toward what's recent.*

Each linked article contributes a weight that halves every ~9 months (`MARKET_SIGNAL_HALF_LIFE_DAYS = 270`) based on its age. An article with no usable date gets a neutral half-weight (never penalized to 0, never rewarded to 1 for missing metadata). The raw decayed sum is then normalized 0–100 against the strongest space currently on the radar, so the metric stays meaningful as the corpus grows.

### 2. Source credibility — 20%
*How trustworthy are the publishers behind the evidence.*

Originally scoped as "source diversity," rejected by the user because of how sources are actually found (diversity isn't the right signal given the collection method). Replaced with a category-anchored trust system:

- `Pipelineteamfile/common/trust.py` — 9 fixed publisher-type categories with fixed anchor scores (100 down to 20: primary institutional feed → peer-reviewed journal → wire service → major press → government body → trade press → think tank → corporate PR → aggregator/unknown). 5 institutional feeds (TED, CORDIS, UK Find a Tender, UK Contracts Finder, Ukraine ProZorro) are hardcoded to the top category, never LLM-assigned.
- `Pipelineteamfile/common/storage.py` — new `sources` table (`source_name`, `category`, `audited_at`, `auditor`, `notes`), auto-seeded as unaudited for every source seen in `articles`.
- `Pipelineteamfile/source_auditor/` — LLM-driven auto-audit pipeline (mirrors the classifier's shape: thread pool, constrained-JSON prompt, retry on invalid category) that categorizes sources behind completed opportunity spaces.
- A space's score is the mean trust score of its linked articles' sources; unaudited sources are excluded from the mean, not counted as 0.

**Bug found and fixed:** `seed_hardcoded_sources()`'s `ON CONFLICT` update didn't set `audited_at`, so the two highest-trust feeds (TED, CORDIS) stayed flagged "unaudited" even after seeding. Since CORDIS alone backs 18/34 classified articles, this silently zeroed out component 2 on almost every space. Fixed by including `audited_at` in the upsert.

### 3. Evidence quality — 20%
*Is the classifier's own confidence trustworthy.*

Repurposes `article_classifications.confidence` (real per-article LLM output, previously computed but unused everywhere). The prompt (`Pipelineteamfile/opportunity_classifier/config/prompt_template.txt`) was rewritten with an anchored rubric — bands for 0.90–1.00 (both taxonomy dimensions explicit), 0.70–0.89 (one explicit, one implied), 0.50–0.69 (both inferred), <0.50 (speculative) — plus a hard rule that a null taxonomy dimension caps confidence at 0.60. This fixed two verified defects in the old field: values clustering near round numbers with no defined meaning, and half-matches scoring as high as full matches.

### 4. Novelty & momentum — 15%
*Is this topic accelerating, relative to everything else on the radar right now.*

`opportunity_spaces` only stores current totals (no history table), so this works from `published_date` alone: articles are bucketed into "last 90 days" vs. "the 90 days before that."

Went through two design passes:
- **v1 (self-comparison):** `score = clamp(50 + pct_change/2, 0, 100)` against the space's own history. Rejected after building it — most spaces on the radar have only 1–2 total articles, so an absolute-percent curve was dominated by noise (going from 1 article to 2 is a meaningless "+100%").
- **v2 (peer ranking, current):** `novelty_momentum_raw()` returns the raw signed growth (`recent_count - prior_count`); `normalize_novelty()` percentile-ranks that value against every other space computed in the same run (fraction of peers with a strictly lower value, half-credit for ties). 50 = exactly median growth this run. This is robust to the small-N problem because the denominator is the whole corpus, not one space's thin history.

The human-facing label ("+42%" / "New" / "—") is untouched by this — it still reports the actual period-over-period percent (or "New" when there's nothing prior to compare, or "—" when there's no dated evidence at all). Only the *weighted score* changed from a fixed curve to a peer rank.

### 5. Strategic relevance — 15%
*Does this fit what Orange Business actually prioritizes.*

New dedicated section in the Company tab (`radar_v2/pages/company.py`) where the taxonomy's `use_case_id`s / `technology_id`s Orange prioritizes are selected (chip toggles, closed taxonomy, wired to `extension_store.orange_priorities()` / `save_orange_priorities()`, new `orange_priorities` table). Explicitly kept separate from the existing customer/prospect company-profile UI — this is Orange's own priority list, not a customer's. Match scoring: both use_case and technology hit → 100, one hit → 50, neither → 0. A space with no Orange priorities configured yet returns `None` (unavailable), not 0.

## Missing-component handling (applies to all 5)

`combine()` excludes any `None` component from the weighted sum and rescales the remaining weights, so a data gap (unaudited sources, no dated evidence, no Orange priorities set) never silently drags a space's score toward zero. The opportunity detail page renders a "Why this score" breakdown — all 5 components with weight, value, and an honest "No data yet" state (with a component-specific reason) instead of a misleading 0.

## Urgency / time horizon (Now · Next · Later) — separate from the score

Originally just a threshold cut on the Attractiveness score itself (`score >= 82 → Now`, etc.) — arbitrary and not really "urgency."

**Replaced (first pass)** with a genuinely deadline-driven calculation, independent of the score: `urgency_horizon()` extracted the real structured date behind a signal — TED's `extra.deadline` (tender close) or CORDIS's `extra.end_date` (funded-project end, parsed despite CORDIS rendering it as an unresolved i18n template like `"31 {{month_03}} 2027"`) — and bucketed the nearest one. That worked, but only TED and CORDIS carried a structured date, so every RSS/gnews/OCDS-evidenced space fell to Later regardless of what its evidence actually said.

**Now superseded (landed).** Horizon is derived from *what kind* of signal a space has, not from a single deadline:

- **Six signal types**, each defined by a distinguishing question answerable from the article text alone: `buying_signal`, `regulation`, `proof_signal`, `competitor_move`, `market_trend`, `tech_maturity`. Tie-break order is `buying_signal > regulation > proof_signal > competitor_move > tech_maturity > market_trend` — the more concrete type wins. Taxonomy and rules live in `Pipelineteamfile/common/signal_types.py`, the single source of truth shared by pipeline and app (same pattern as `common/trust.py`).
- **Deterministic per source.** TED / OCDS (UK, Ukraine) / SAM.gov → `buying_signal` at confidence 1.0, no LLM judgment. CORDIS → driven by the project's own `status` field (`SIGNED`/`CLOSED`/`TERMINATED`, verified live) plus its published-result count, at confidence 0.9. Only RSS goes to the model, with source and vertical passed as a hint that never overrides a distinguishing question.
- **Same single-shot call.** The six new fields (`signal_type`, `signal_type_confidence`, `signal_date`, `event_date`, `event_date_precision`, `signal_type_rationale`) were added to the existing constrained-JSON classification, not a new pipeline stage. The signal-type enum is enforced with a retry; an unparseable response fails the record for review rather than being coerced.
- **Per-signal prior**, then aggregation. `buying_signal`/`proof_signal` → Now; `competitor_move`/`market_trend` → Next; `tech_maturity` → Later; `regulation` depends on its `event_date` (≤6mo or in force → Now, 6–24mo → Next, beyond/absent/imprecise → Later). Confidence below 0.5 demotes the prior one step, so a low-confidence signal can never trigger Now on its own.
- **Now requires convergence**: ≥2 Now-prior signals, from ≥2 distinct sources, at least one within 90 days. **Next** catches concrete evidence that misses that bar (a single tender, two from the same feed, nothing recent) *or* ≥2 forward-looking signals within 180 days — which is what makes the middle band reachable at all. Everything else is **Later**. Every threshold is configuration (`HorizonConfig`), not a literal.
- **Explainable.** The counts per prior, the distinct-source count and the rule that fired are persisted on `opportunity_spaces` and rendered as a "Why this timing" panel next to "Why this score".

## Files touched (this thread of work)

- `radar_v2/services/attractiveness.py` — score engine (new); the old `urgency_horizon()` and its date helpers were removed from here
- `radar_v2/services/horizon.py` — app-side Now/Next/Later, reading only signal types, dates, sources and confidences
- `Pipelineteamfile/common/signal_types.py` — signal-type taxonomy, horizon priors, aggregation rules, thresholds
- `Pipelineteamfile/opportunity_classifier/collector/signal_route.py` — deterministic per-source routing
- `Pipelineteamfile/opportunity_classifier/fixtures/signal_type_golden_set.json` — 60 self-labeled examples, **pending human review**
- `radar_v2/services/team_repository.py` — wiring into `list_opportunities()`
- `radar_v2/services/extension_store.py` — `orange_priorities` table + accessors
- `radar_v2/models.py`, `radar_v2/state.py` — new fields (`breakdown`, `horizon_reason`, etc.)
- `radar_v2/pages/opportunities.py`, `radar_v2/pages/opportunity_detail.py`, `radar_v2/pages/company.py`, `radar_v2/pages/help.py` — UI
- `radar_v2/components/ui.py` — breakdown row / priority chip components
- `Pipelineteamfile/common/trust.py`, `Pipelineteamfile/common/audit_source.py`, `Pipelineteamfile/common/storage.py` — source trust infra
- `Pipelineteamfile/source_auditor/` — LLM source-audit pipeline
- `Pipelineteamfile/opportunity_classifier/config/prompt_template.txt`, `.../collector/select_corpus.py` — confidence rubric, fail-status exclusion
- `docs/scoring_requirements_gap_analysis_2026-08-25.pdf` — the original audit that triggered this whole redesign

Nothing in this thread of work has been committed; it's sitting in the working tree for review.
