# Cobalt Data Society Innovation Radar — Project Briefing

Written 2026-08-27 for onboarding another agent onto this project. Precise, not a summary of intent — every claim below was verified against the actual code/data at the time of writing, not assumed.

## 1. What this is

A business-facing "innovation radar": it automatically collects institutional signals (government procurement notices, EU research grants, news) from real external sources, uses an LLM to classify each one against a closed business taxonomy, groups them into **opportunity spaces** (Vertical × Use Case × Technology triples), and scores/explains each one for a human reader (strategist, salesperson, or presales engineer) deciding what to act on.

Two top-level parts in the repo root (`c:\Users\danuk\OneDrive\beta app`):
- **`Pipelineteamfile/`** — the data pipeline. Collects, classifies, scores raw evidence. Standalone Python, has its own venv-independent modules, own SQLite DB.
- **`radar_v2/`** — the Reflex (Python web framework) app. Reads that same SQLite DB, no direct write access except through the pipeline's own storage functions it imports.

Both share one virtualenv at `.venv/` (repo root) and one `requirements.txt`.

## 2. The data pipeline (`Pipelineteamfile/`)

### 2.1 Sources and collection
- **TED** (EU procurement notices), **CORDIS** (EU research/innovation grants), **OCDS UK** and **OCDS Ukraine** (procurement) — all live, free public APIs, collected across 14 fixed verticals (Manufacturing, Retail, Finance/Banking/Insurance, Public/Gov sector, Defense, Automotive, Transportation & Construction, Lifesciences, Energy, Wholesale, Media & Entertainment, Healthcare, Natural Resources, Aerospace).
- **RSS** and **Google News (gnews)** also exist as source types in the schema, but **gnews is explicitly paused** as a source (`opportunity_classifier/collector/select_corpus.py` excludes it from the classification pool entirely — "paused as a source, see dark_corner.md").
- Collection is orchestrated by **`Pipelineteamfile/run_radar.py`**, a 5-stage pipeline:
  1. **Collect** — `ted_collector`, `cordis_collector`, `ocds_collector` each run per-vertical.
  2. **Select corpus** — `opportunity_classifier/collector/select_corpus.py` rebuilds the `classification_pool` table **from scratch every run** (deletes and re-selects up to 600 articles/vertical, balanced TED-backbone / CORDIS-OCDS-fill / RSS-backfill, recent/1y/5y mix). It is not additive.
  3. **ML noise filter** — `opportunity_classifier/mlfilter` scores articles for relevance; skipped ("bootstrap") until there are ≥5 `classified`/`needs_review` and ≥5 `no_match` labels to train against.
  4. **Classify** — `opportunity_classifier/collector/main.py`'s `run()` sends each pending pool article to the LLM (env var `NAVY_MODEL`, currently `glm-5.1` via an OpenAI-compatible endpoint at `NAVY_BASE_URL`). **No cap by default** (`--limit` omitted = process the entire pending pool; this was a deliberate change this session, see §6).
  5. **Summarize** — writes a JSON run summary to `Pipelineteamfile/logs/radar_runs/{run_id}.json` and recomputes `opportunity_spaces`.
- A lock file at `Pipelineteamfile/data/pipeline.lock` (PID + mtime) prevents concurrent runs; written at the very start of `run()`, removed in a `finally` regardless of success/failure — this is the authoritative "is a run active right now" signal used throughout the app.

### 2.2 The taxonomy (closed vocabulary, `opportunity_classifier/config/taxonomy.json`)
- **Verticals**: the 14 above.
- **Use cases** and **Technologies**: closed lists (~27 use cases, ~21 technologies at last count). The classifier is instructed to never invent an id; null is a valid answer for either dimension.
- **Business domains** (6): `ox-smart-industries` ("OX: Smart Industries" — real Orange Business branding, not a typo), `connectivity-solutions`, `cybersecurity`, `cloud`, `cx-customer-experience`, `ex-employee-experience`. Derived deterministically per space from its use_case/technology via mapping tables in `common/business_domains.py` / `radar_v2/services/domains.py`.
- **Personas**: a weighted use-case × persona table with domain overlay, feeding both filtering and a "dampened" ranking multiplier (`common/personas.py` / `radar_v2/services/personas.py`).
- **Signal types** (6, closed): `buying_signal`, `regulation`, `proof_signal`, `competitor_move`, `market_trend`, `tech_maturity` (`common/signal_types.py`). Tie-break priority when an article plausibly fits more than one, in that exact order.
  - **Deterministic** for TED, OCDS (UK/Ukraine), CORDIS — derived mechanically from the record itself (feed identity for TED/OCDS = always `buying_signal`; CORDIS project status via its own public API = `proof_signal`/`tech_maturity` depending on status+results). No LLM call, no cost.
  - **LLM-classified** for RSS/GNews — the model decides.
  - `opportunity_classifier/collector/signal_route.py` (deterministic) and `.../client.py` (LLM) both populate two parallel text fields per article: `signal_type_rationale` (analyst-toned, why this type was chosen) and `signal_type_plain_summary` (plain-language restatement of the underlying fact, for non-technical readers — added this session, see §6).
- **Geography**: countries (ISO alpha-2) + region roll-up. Deterministic for TED/OCDS/CORDIS (field extraction), LLM-inferred for RSS. `common/geography.py`.

### 2.3 Database
SQLite at `Pipelineteamfile/data/articles.db` — **gitignored, local-only, not the same file as what's deployed to Fly.io** (see §7). Key tables: `articles` (raw collected records), `article_classifications` (one row per article: taxonomy match, confidence, signal type, geography, plain summary), `classification_pool` (the current balanced selection — rebuilt every run, not historical), `opportunity_spaces` (aggregated per Vertical×UseCase×Technology triple), `opportunity_space_domains`/`_personas`/`_regions` (join tables), `ml_noise_scores`, `sources` (trust/audit metadata).

**Live counts as of this writing**: 5,504 articles collected (grew substantially during this session's testing — see caveat in §8), 547 classified, 311 opportunity spaces. **Every classified article has `signal_type` and `signal_type_plain_summary` populated (0 missing)** — this was a real gap fixed this session (§6). There is currently a large backlog: ~4,957 collected-but-unclassified articles, because collection outpaced classification during testing. The next full pipeline run will have a lot of work to do.

## 3. The scoring model (`radar_v2/services/attractiveness.py`)

Three **independent** outputs per opportunity space — never blended into one number:

### 3.1 Attractiveness score (0-100)
Weighted sum of 4 components, each independently computable; a missing component is **excluded and the remaining weights rescaled**, never counted as zero (`combine()`). Current weights (renormalized after strategic relevance was pulled out into Orange Fit — see below; base weights were 30/20/20/15 out of an original 5-part 30/20/20/15/15 deck spec):
- **Market signal strength — 35%**: recency-weighted density of linked evidence (half-life ~270 days / 9 months).
- **Source credibility — 24%**: mean trust score of the sources behind the space's articles (`Pipelineteamfile/common/trust.py`, category-anchored, falls back to a source-type prior if a source hasn't been audited yet).
- **Evidence quality — 24%**: blends real per-article classifier confidence (when ≥50% of the space's articles have it) with an always-available fallback built from article count + source independence + mean trust — so a space with zero classifier confidence still gets a real number, never "unavailable."
- **Novelty & momentum — 18%**: period-over-period (90-day buckets) growth in dated evidence.

### 3.2 Orange Fit / right-to-win score (0-100) — standalone, never enters the Attractiveness sum
`orange_fit()`, two paths:
- **Explicit match** (once Company → Orange priorities has anything selected): compares the space's use_case/technology against your selected priority sets. Both dimensions configured → 100/50/0 for both/one/neither match. Only one dimension configured → 100/0, no partial credit.
- **Domain-coverage fallback** (while nothing is configured): `min(domain_count, 4) / 4 × 100` — a weaker capability-breadth proxy, deliberately phrased differently in the UI so it's never mistaken for a real priority match.
- Surfaces in: the Orange Fit section on every space's detail page, the Presales role mode's sort key, and (added this session) the "why this matters" explanation's second clause.

### 3.3 Now/Next/Later horizon — independent of both scores above
`radar_v2/services/horizon.py`. Deadline-driven, not score-threshold-driven: based on the nearest real tender-close/project-end date found in the evidence, converging signal types, and source diversity. Deliberately reads nothing derived from `attractiveness.py`.

### 3.4 Radar/Watchlist publication gate — also independent
`radar_watchlist_gate()`. Pure evidence-independence check (≥2 independent sources, ≥2 independent events, ≥45 confidence) ported from the team's own `Analysis/05_score_opportunities.py`. Decides a badge/filter chip, doesn't hide anything.

## 4. Explanation fields (`radar_v2/services/explanations.py`)

Three deterministic, composed-not-generated fields per space — **no LLM call at render time**, built from typed clauses:
- **Why hot now** — 0-3 clauses, one per qualifying signal (typed, dated, within the 365-day recency window), ordered by signal-type tie-break priority then recency. Each clause = a fixed lead-in phrase + the classifier's `signal_type_plain_summary` (falls back to a truncated `signal_type_rationale` for any row predating that field). Duplicate clauses collapse (deterministic sources like CORDIS repeat the same rationale across rows).
- **Why this matters** — always exactly 2 clauses. Clause 1: a domain-framing template ("A Cloud opportunity for {vertical}"). Clause 2: right-to-win phrases if any exist (`right_to_win_phrases()` — **always empty today**, no CRM/account/deal/reference-case data source exists anywhere in this codebase), else falls back to the space's own Orange Fit tier (strong/partial/none/not-configured — wired this session).
- **Recommended move** — a map keyed by role mode (strategist/sales/presales each get a genuinely different sentence for the same space): a base clause from a role-mode × horizon matrix + an action clause keyed on the dominant (highest-ranked) signal type, the same one "why hot now" ranked first — the two fields are guaranteed to never disagree.

## 5. The app (`radar_v2/`)

- **State**: single `RadarState(rx.State)` in `radar_v2/state.py` — large, holds essentially all UI state (opportunities list, filters, company profile, documents, discovery, reports, pipeline status, settings).
- **Pages** (`radar_v2/pages/`): `overview.py` (dashboard, 3 metric cards after this session — "Needs attention" was removed), `opportunities.py` (filterable list), `opportunity_detail.py`, `company.py` (customer profile + Orange's own priorities), `sources.py`, `discovery.py` (ad-hoc web search → promote into pipeline), `reports.py` (LLM-generated business reports per space, via Tavily/SearXNG web search), `refresh.py` ("Run full radar update" button — heavily reworked this session, see §6), `settings.py`, `help.py`.
- **Role modes** (`radar_v2/services/role_modes.py`, config in `radar_v2/config/role_modes.json`): Strategist / Sales / Presales. Pure view configuration — default filters, sort key, which page regions lead/standard/collapsed. Never changes what's computed, only what's emphasized. Presales sorts by Orange Fit; Sales by persona-weighted score; Strategist by Attractiveness.
- **`team_repository.py`** is the read boundary between the app and the pipeline's SQLite DB — every page ultimately calls into here.

## 6. What changed this session (chronological, high-level)

1. **Fixed a real data-completeness bug**: a bulk import script (`_import_all_spaces.py`, 309 spaces from an external "Pipeline Opportunity" export) had written 507 articles with placeholder classifications missing `signal_type`/geography, and a follow-up backfill script silently no-op'd due to a pool-membership bug. Fixed the bug, backfilled all 548 articles (344 free/deterministic, 166 via the paid classifier — user-approved spend).
2. **Added `signal_type_plain_summary`**: end-to-end (prompt, deterministic templates, storage, `explanations.py`), so "why hot now" shows plain language instead of truncated analyst text. Backfilled all 548 articles (375 free, 173 via a small rewrite-only LLM call, not a full reclassification).
3. **Wired Orange Fit into Presales sort** (`FIT_SCORE_AVAILABLE` flipped True) and into the "why this matters" right-to-win clause (tiered instead of one static sentence).
4. **Removed the dead "Right to win & proof points" placeholder region** from the detail page and role-mode config (a different, still-unbuilt CRM-data feature — not the same thing as Orange Fit).
5. **Fixed stale claims** that Orange priorities feed the old 5-component "strategic relevance (15%)" Attractiveness score — they don't; they drive the standalone Orange Fit score. Fixed in the Company tab callout, the Help page glossary (which had the literal wrong percentages), and two code comments.
6. **Removed the classifier cap** — a full run now always classifies the entire pending pool, no 5-100 slider ceiling.
7. **Renamed self-branding** from "Orange Business" to "Cobalt Data Society" in the homepage browser tab title and the sidebar's top kicker specifically (not elsewhere — README/docs untouched, that was a separate scope decision).
8. **Deployed to Fly.io** (see §7) after Reflex Cloud's own deploy API proved to have a genuine server-side 500 bug (exhaustively diagnosed, not fixable client-side).
9. **Fixed the local "Run full radar update" button's reliability** — twice. First pass made `run_pipeline` an `@rx.event(background=True)` task with a proper async subprocess reader (fixed the event-loop-starvation cause of "Cannot connect to server: timeout"). User reported it still restarted after a disconnect, so it was redesigned again: the button now launches `run_radar.py` as a **fully OS-detached process** (`pipeline_runner.launch_detached()` — Windows `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`), independent of the Reflex backend process itself. A separate lightweight background task (`poll_pipeline_status`) watches the detached run's lock file and log purely as an observer — losing that observer (session drop, page reload) never touches the run. `load()` also now detects an already-running detached pipeline on any fresh page load (via the lock file, not in-memory state) and resumes watching it, so the page never lies about "Ready" when a run is genuinely still going. **This mechanism was directly verified working** (detachment survives the launcher process exiting; live progress correctly read from the log file) via a real test run this session, separate from what the user confirmed working themselves in the browser.

## 7. Deployment

- **Fly.io**: `cobalt-data-society-radar`, region `lhr` (London), live at **https://cobalt-data-society-radar.fly.dev/**. Single machine, `min_machines_running=1`/HA disabled (deliberate — Reflex holds session state in memory with no Redis, so 2 machines would randomly drop sessions). Image ~292 MB.
  - **Redeploy command**: `flyctl deploy --remote-only --ha=false` from repo root (the `--ha=false` matters or Fly quietly re-adds a second machine). `flyctl` is at `C:\Users\danuk\.fly\bin\flyctl.exe`, not on PATH by default.
  - **`sentence-transformers`/`torch` are deliberately excluded** from the deployed image (`requirements-deploy.txt`, separate from `requirements.txt`) — only used by a lazy-imported ML noise-filter module the Reflex UI itself never touches. If a future pipeline run on Fly ever needs that path, it'll ImportError there specifically; local dev is unaffected.
  - **Secrets set on Fly**: `NAVY_API_KEY`, `NAVY_BASE_URL`, `NAVY_MODEL`, `TAVILY_API_KEY`. **`SEARXNG_URL` is deliberately not set** — it points at `localhost:8888`, meaningless on a remote server, so SearXNG-based search doesn't work there (Tavily does).
  - **Critical caveat**: the Fly image has **no persistent volume**. Its copy of `articles.db` is whatever was baked in at the last `flyctl deploy` — it does not sync with the local DB in either direction, and any pipeline run executed *on* Fly would be lost on the next restart/redeploy. Nobody has run the pipeline on Fly; all real data work happens locally.
  - Reflex Cloud's own `reflex deploy` path was tried first and **abandoned** — `build.reflex.dev`'s deployment-creation endpoint returns a genuine server-side `500 Internal Server Error` on every attempt (validated via ~25 varied requests, ruling out every client-side variable). Not worth retrying without checking if Reflex has fixed it.
- **Local**: `start.bat` (Windows) sets up the venv, installs `requirements.txt`, runs `reflex run` (ports 3030 frontend / 8031 backend, per `rxconfig.py`). Repo lives inside OneDrive, which causes **intermittent EBUSY file-lock errors** during npm/node operations (hot-reload cleanup, sometimes a full deploy build step) — usually transient and clears on retry; occasionally kills the dev server's frontend worker and needs a manual restart.

## 8. Known gaps / things to watch

- **Right-to-win / CRM data genuinely does not exist.** `RIGHT_TO_WIN_ELEMENTS` (accounts, recent deals, reference cases, offering match, partner match) is a defined contract in `explanations.py` that nothing populates. This is *not* the same thing as Orange Fit (which is real and wired) — don't conflate the two if asked to "improve right-to-win" again; clarify which one is meant.
- **Local DB has a large classify backlog right now** (~4,957 unclassified articles out of 5,504) from this session's repeated test collection runs. The next full run will be a big one (all 14 verticals × TED+CORDIS+OCDS collection, uncapped classification of ~5k pending articles) — expect it to take a long time and cost real tokens.
- **Uncommitted local changes exist as of this writing**: `radar_v2/pages/overview.py`, `radar_v2/services/pipeline_runner.py`, `radar_v2/state.py` (the detached-process fix) are modified but not committed; `Dockerfile`, `.dockerignore`, `fly.toml`, `requirements-deploy.txt` are untracked (never committed at all). Check `git status` before assuming the working tree matches the last push (`acf8360`).
- **GNews is paused as a source** — collected historically but excluded from new classification pool selection.
- **No signal_type_plain_summary quality guarantee for future articles from sources not yet covered by the rewritten prompt/templates** — if a new source type is ever added, it needs both a `signal_type_rationale` and a `signal_type_plain_summary` path (deterministic template or prompt field) or it'll silently fall back to truncated rationale text.
- **`classification_pool` is rebuilt from scratch every pipeline run**, not additive — don't assume a space's article set only grows monotonically between runs in ways tied to the pool table specifically (article_classifications itself is additive/permanent; the pool is just a selection mechanism).

## 9. Key files quick-reference

| Concern | File |
|---|---|
| Full pipeline orchestration | `Pipelineteamfile/run_radar.py` |
| LLM classification | `Pipelineteamfile/opportunity_classifier/collector/{main,client}.py` |
| Deterministic signal typing | `Pipelineteamfile/opportunity_classifier/collector/signal_route.py` |
| Geography resolution | `Pipelineteamfile/opportunity_classifier/collector/geo_route.py`, `common/geography.py` |
| Classifier prompt | `Pipelineteamfile/opportunity_classifier/config/prompt_template.txt` |
| Taxonomy | `Pipelineteamfile/opportunity_classifier/config/taxonomy.json` |
| DB schema/storage | `Pipelineteamfile/opportunity_classifier/collector/storage.py` |
| Attractiveness / Orange Fit / horizon gate | `radar_v2/services/attractiveness.py` |
| Now/Next/Later | `radar_v2/services/horizon.py` |
| Explanation fields | `radar_v2/services/explanations.py` |
| Role modes | `radar_v2/services/role_modes.py`, `radar_v2/config/role_modes.json` |
| App ↔ DB read boundary | `radar_v2/services/team_repository.py` |
| Detached pipeline launch/status | `radar_v2/services/pipeline_runner.py` |
| Main state | `radar_v2/state.py` |
| Page routes | `radar_v2/radar_v2.py` |
| Fly deploy config | `Dockerfile`, `fly.toml`, `.dockerignore`, `requirements-deploy.txt` |
| Tests | `tests/` (216 passing as of this writing) |

## 10. How to verify any of this yourself

- Run the test suite: `.venv\Scripts\python.exe -m pytest tests/ -q` from repo root.
- Check live local DB stats: open `Pipelineteamfile/data/articles.db` with sqlite3 directly.
- Check what's actually deployed vs. committed: `git log --oneline -5`, `git status`, and compare against `https://cobalt-data-society-radar.fly.dev/`.
- Don't trust any specific number in this document as current without re-checking — the DB in particular changes every time a pipeline run happens.
