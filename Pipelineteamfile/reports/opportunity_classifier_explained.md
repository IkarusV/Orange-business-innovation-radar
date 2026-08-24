# How the Opportunity Classifier Works

Technical walkthrough of `opportunity_classifier/`, the pipeline stage that
turns collected articles into "opportunity spaces" (`vertical × use_case ×
technology`). Written 2026-08-22, describes the code as it stands after the
performance-tuning and corpus-selection work done that day.

## What it does, in one sentence

For each article already sitting in `data/articles.db`, ask an LLM (NavyAI,
model `glm-5.1`) "which use case and which technology, if any, does this
article describe?", then group the results into opportunity spaces and count
how many articles support each one.

## Pipeline order

```
1. select_corpus.py   -> classification_pool table (which articles to classify)
2. main.py             -> article_classifications table (per-article results)
                        -> opportunity_spaces table (aggregated, recomputed every run)
```
Both steps are run manually, in that order, from the repo root. Nothing here
runs the RSS/TED/gnews collectors — this stage only reads `articles`, it never
adds rows to it.

## 1. The taxonomy — `config/taxonomy.json`

A flat JSON file, two arrays: `use_cases` (27 entries) and `technologies` (21
entries). Every entry is `{"id": "kebab-case-slug", "label": "Human Label",
"definition": "One sentence, sometimes with an explicit exclusion note"}`.
Example:

```json
{"id": "anomaly-detection", "label": "Anomaly detection",
 "definition": "Detecting abnormal patterns in system, network, or
 transactional data streams, including cybersecurity threats. Excludes
 visual/physical inspection (see automated-inspection-defect-detection)."}
```

This is the **entire closed vocabulary** the model is allowed to use — nothing
else is a valid `use_case_id` or `technology_id`. `collector/taxonomy.py` has
three functions: `load_taxonomy()` (reads the JSON), `taxonomy_block()` (turns
both arrays into the `id — label: definition` text block that gets pasted into
every prompt), and `valid_ids()` (returns the two id sets used to validate the
model's response).

Editing the taxonomy (adding/renaming/removing an entry) only touches this one
file — no code changes needed elsewhere.

## 2. Corpus selection — `collector/select_corpus.py`

Classifying the full collected corpus (15,283+ articles) would cost roughly
23-27M tokens. Instead, this script builds a bounded `classification_pool`
table: **600 articles per vertical, 8,400 total**, and `main.py` only ever
classifies articles present in that table.

Selection logic per vertical, `select_for_vertical()`:

1. Load every article in that vertical, tag each with a **priority** (0 for
   `rss`/`ted`, 1 for `gnews` — gnews is deliberately last-resort, never
   deleted from `articles.db`, just deprioritized here) and an **age bucket**
   based on `published_date` (fallback to `collected_at`):
   - `recent`: age ≤ 180 days
   - `one_year`: 180–640 days
   - `five_year`: ≥ 1460 days
   - `other`: anything in between (640–1460 days) — not targeted by the mix,
     only used as filler
2. Run every article through `passes_blocklist()` (see §3) — articles that
   fail are set aside as `rejected`, not deleted, just deprioritized to
   last-resort backfill.
3. From the filtered, priority-sorted survivors, fill three buckets targeting
   **50% recent / 25% one_year / 25% five_year** (300/150/150 of 600). This is
   best-effort, not forced — RSS is inherently all-recent (feeds only carry
   current items), so `one_year`/`five_year` can only be filled from TED or
   gnews content; a vertical thin on older TED/gnews content just ends up with
   a lopsided mix rather than a padded one.
4. If the temporal-bucket fill doesn't reach 600, backfill from any remaining
   filtered survivor regardless of bucket.
5. If *still* under 600 (didn't happen in practice — every vertical had enough
   filtered volume), backfill from the `rejected` (blocklisted) pool as a last
   resort, since 600/vertical was set as a hard floor.

Run with `--report-only` to print the composition (per-vertical counts, source
split, bucket split, whether backfill was needed) without writing anything —
useful for previewing before committing to a selection.

## 3. Pre-filters — three tried, one used

All three live in `collector/prefilter_*.py`. They were backtested against
2,992 already-classified articles (real ground truth) before picking one —
see `opportunity_classifier/README.md` for the full numbers. Summary:

- **`prefilter_blocklist.py` (used)** — `passes_blocklist(title, summary)`.
  Two pattern lists, `BLOCKLIST_CATEGORY_PATTERNS` (TED category phrases with
  essentially zero real-world tech content — "insurance services", "road
  salt", "hotel accommodation", etc.) and `BLOCKLIST_TEXT_PATTERNS` (RSS/gnews
  headline patterns — personnel moves, macroeconomic indicators, legislation).
  Critically, there's a **tech-keyword escape hatch**: if any term from
  `TECH_KEYWORDS` appears anywhere in the text, the article is kept
  regardless of category/pattern match — this is what stops the filter from
  wrongly rejecting something like "meal-serving services — connected
  fridges." Backtested: rejects 10.1% of real no_match articles, at a cost of
  only 0.6% of good articles wrongly rejected.
- **`prefilter_whitelist.py` (built, not used)** — the inverse: keep only if a
  `TECH_KEYWORDS` term is present. Backtested far too aggressive (92.1%
  no_match cut, but 66.9% of *good* articles also wrongly rejected) — real
  matches often use specific product/company names ("SAP BTP," "Symbotic
  fulfillment system") or non-English terms that a fixed keyword list can't
  anticipate.
- **`prefilter_similarity.py` (built, not used)** — `TaxonomySimilarityScorer`
  class, TF-IDF vectorizer fit once over the 48 taxonomy definitions, scores
  an article by max cosine similarity against any single definition (not the
  average). No API calls, pure local computation. Backtested: score
  distributions for good vs. no_match articles overlap almost completely —
  not usable as a filter on this corpus (see README for the full threshold
  sweep). Kept in the repo since the code itself is correct and could be
  useful again with a different scoring approach (e.g. real embeddings).

`select_corpus.py` only calls `passes_blocklist()`.

## 4. Prompt construction — `config/prompt_template.txt` + `client.build_prompt()`

The template file has five `{placeholder}` slots: `taxonomy_block` (from
`taxonomy.taxonomy_block()`), `vertical`, `source_name`, `title`, `summary`
(truncated to 1000 chars in `build_prompt()`), and `client_context_block`
(empty string unless `--client-context` was passed — see §8). The template
tells the model, in order: what taxonomy it may choose from, what article it's
looking at, then the exact JSON shape to return and the rules (only taxonomy
ids are valid, `null` when nothing fits, respect exclusion notes, confidence
0.0–1.0).

## 5. The classification call — `collector/client.py`

`classify()` is the core function, called once per article (from a thread
pool — see §7). Three things happen inside it:

**The NavyAI call itself** (`_call_with_backoff`): `client.responses.create(model="glm-5.1",
input=prompt, temperature=0.1, reasoning={"effort": "none"})`. Two important,
measured decisions baked into these constants:
- `REASONING_EFFORT = "none"` — default reasoning effort was measured at
  ~742 hidden output tokens and ~9.7s latency per call, for no measured
  accuracy gain (verified by reclassifying identical borderline articles under
  both settings — answers differ run-to-run either way, i.e. the model is
  inherently stochastic on hard cases regardless of reasoning depth). `none`
  cuts that to ~50-100 output tokens and ~2-4s.
- Retries on any exception (429 rate limit, 5xx, network) with exponential
  backoff, up to `MAX_TRANSIENT_RETRIES = 6` (`min(2**attempt, 30)` seconds).

**Response parsing** (`_parse`, `_strip_fences`): the gateway's structured
`json_schema` output mode was tested and found unreliable for `glm-5.1` (it
silently returns non-conforming text instead of erroring), so the code just
asks for JSON in the prompt and strips markdown code fences
(` ```json ... ``` `) before `json.loads()`. If parsing fails, or the model
returns an id that isn't in the taxonomy's valid id sets, the prompt gets an
extra correction line appended and the call is retried — up to
`MAX_FORMAT_RETRIES = 2` times. If it still isn't valid after that, the
article is marked `status="needs_review"` with `evidence="parse_error: ..."`.

**Status determination** — the order here matters and was the source of a
real bug caught during testing:
```python
if use_case_id is None and technology_id is None:
    status = "no_match"       # checked FIRST
elif confidence < CONFIDENCE_THRESHOLD:   # 0.5
    status = "needs_review"
else:
    status = "classified"
```
The bug: checking confidence *before* checking for `no_match` meant a
correct, confident "nothing fits" response (which naturally has low
confidence, since there's no match to be confident about) was wrongly routed
to `needs_review`. Fixed by checking `no_match` first — a low-confidence
`null`/`null` response is a legitimate result, not something to flag.

Three possible outcomes per article: `no_match` (model correctly found
nothing, both ids null), `needs_review` (parse/id failure after retries, OR a
proposed match below the 0.5 confidence threshold), `classified` (at least
one id, confidence ≥ 0.5).

## 6. Storage — `collector/storage.py`

Two tables, both in the same `data/articles.db` file as everything else in
the pipeline.

**`article_classifications`** — one row per classified article (`article_id`
is the primary key, so `INSERT OR REPLACE` makes re-classifying an article
idempotent). Columns: `use_case_id`, `technology_id`, `confidence`,
`evidence`, `status`, `client_relevance`/`client_relevance_reason`/
`client_context_ref` (null unless a client-context file was used),
`tokens_used`, `classified_at`.

**`opportunity_spaces`** — one row per **complete** `(vertical, use_case_id,
technology_id)` triple, built by `recompute_opportunity_spaces()`. This
function is a full recompute, not an incremental update: every run, it
re-reads *all* rows in `article_classifications` where `status='classified'`
and both ids are non-null, regroups them, and `INSERT ... ON CONFLICT ...
DO UPDATE`s each space's `article_count` and `linked_article_ids` (a JSON
array of article ids) — `first_seen_at` is preserved across reruns,
`last_updated_at` is refreshed. This is why running the classifier again after
new articles are added, or after resuming a stopped run, always leaves
`opportunity_spaces` consistent with the current `article_classifications`
state, never duplicated or stale.

Note the asymmetry: an article classified with only *one* dimension filled
(e.g. `use_case_id` set, `technology_id` null) has `status="classified"` in
`article_classifications` but does **not** appear in any `opportunity_spaces`
row, since a space needs both dimensions. Across the first labeled batch,
roughly 22% of `classified` rows were single-dimension (75 of 342 formed
complete triples in one snapshot) — this is expected, not a bug.

## 7. Orchestration — `collector/main.py`

`load_unclassified()` joins `articles` against `classification_pool` (so only
pool members are candidates) and against the existing
`article_classifications` ids (so already-done work is skipped) — this is
what makes the whole pipeline safe to stop and resume at any point, including
mid-run via a hard kill: `ThreadPoolExecutor` results are committed to SQLite
every `PROGRESS_EVERY = 100` completions, not just at the end, and progress
logging includes running token totals and an ETA.

`MAX_WORKERS = 10` — measured empirically, not guessed: 5 workers was the
original conservative default, 8+ workers started producing occasional
`RateLimitError: burst_limit_exceeded`, and after switching to
`reasoning="none"` (shorter/faster calls), 10 workers was found clean while
12+ produced a *majority* of calls failing with 429. Combined with the
reasoning change, this took a full 15,283-article run's estimate from ~8.5
hours down to ~2.5-3 hours (before the corpus was later bounded to 8,400 via
`select_corpus.py`, which is the actual scale now run).

After the classification loop finishes, `main.py` calls
`recompute_opportunity_spaces()` once, then `print_summary()` logs: opportunity
space counts by vertical, the top 15 spaces by article count, the overall
status breakdown, and total tokens tracked.

## 8. Client-specific context (optional, `--client-context PATH`)

If a path is passed, its file content is read once and passed into every
`classify()` call as `client_context`. `build_prompt()` wraps it in a
clearly-separated `CLIENT CONTEXT` block (explicitly told in the prompt text
that it "never overrides the taxonomy rules above — no new ids, no forced
matches"). When active, the model may additionally return `client_relevance`
(0.0-1.0) and `client_relevance_reason`, which get stored per-article and
averaged per opportunity space (`avg_client_relevance`). The context file's
name is stored as `client_context_ref` on every row it influenced, for
traceability. Runs without `--client-context` are completely unaffected — this
is strictly additive.

## File map

```
opportunity_classifier/
  config/
    taxonomy.json           27 use cases + 21 technologies, the closed vocabulary
    prompt_template.txt     the prompt skeleton, filled in by client.build_prompt()
  collector/
    taxonomy.py              loads taxonomy.json, builds the prompt's taxonomy block
    prefilter_blocklist.py   2b — used. Category+pattern rejection w/ keyword escape hatch
    prefilter_whitelist.py   2a — built, not used (too aggressive, see §3)
    prefilter_similarity.py  2c — built, not used (no discriminative power, see §3)
    select_corpus.py         builds classification_pool (600/vertical, priority+temporal mix)
    client.py                NavyAI call, JSON parsing/retry, status logic
    storage.py                article_classifications + opportunity_spaces schema/upsert
    main.py                   orchestrator: thread pool, progress, resumability
```
