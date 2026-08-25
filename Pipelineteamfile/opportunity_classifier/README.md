# Opportunity Space Classification

Classifies already-collected articles against a Use Case × Technology taxonomy
and aggregates matches into opportunity spaces (`vertical × use_case ×
technology`), via the NavyAI API (`https://api.navy/v1`, OpenAI SDK, Responses
API, model `glm-5.1`). Unpaused and built 2026-08-22.

## Non-LLM classification attempt: Route 1 (tried and discarded, 2026-08-22)

A free, zero-token rule-based classifier — English-only, 20 curated
terms/entry (48×20), per-language keyword tables with `langdetect`-based
language routing — was built and run on all 15,283 articles (34 seconds,
$0). Backtested against the 4,676 English articles the LLM had already
classified: **recovered only ~31% of the LLM's real matches** (116 full +
62 partial agreement out of 572 LLM positives), with real false-positive
noise on top (e.g. "aml" substring-matching inside "streamlines"). Discarded
in favor of a supervised ML approach (in planning) trained on the LLM's own
labels rather than hand-curated keyword lists. Code was removed; if you want
the numbers behind this decision, they're preserved in this session's
history/memory, not in the repo.

## Run

```
python -m opportunity_classifier.collector.select_corpus   # builds classification_pool first
export NAVY_API_KEY=...      # never commit this
export NAVY_BASE_URL=https://api.navy/v1
python -m opportunity_classifier.collector.main
```

Run from the repo root. `main.py` only classifies articles present in the
`classification_pool` table (see "Corpus selection" below) — run
`select_corpus.py` first, or nothing will be classified. `--limit N` classifies
at most N unclassified pool articles (useful for validation before a full run).
`--client-context PATH` injects a client-specific context file into every
prompt (see below).

Idempotent and incremental: already-classified articles (present in
`article_classifications`) are skipped, so it's safe to stop and resume, or
re-run after new articles/a new pool selection arrives — only new/unclassified
pool rows get processed, and `opportunity_spaces` is fully recomputed from all
classified rows every run.

## Corpus selection (2026-08-22)

The full collected corpus (15,283+ articles) costs too many tokens to classify
in full (~23-27M). `select_corpus.py` picks a bounded pool instead:

- **600 articles per vertical, hard floor** (8,400 total) — chosen over
  classifying everything.
- **RSS/TED prioritized over gnews** — gnews is lowest priority, only used to
  fill a vertical's 600 slots if RSS+TED alone falls short (rare: only 1 of 14
  verticals, Finance/Banking/Insurance, even has 600 RSS+TED articles on its
  own without any gnews). gnews articles are never deleted from `articles.db`,
  just deprioritized for classification.
- **2b (blocklist) filtering** applied first — see below for why 2a and 2c
  aren't used.
- **Best-effort 50%/25%/25% recent/~1y-ago/~5y-ago mix**, not forced — RSS is
  inherently all-recent (feeds only carry current items), so the 1y/5y buckets
  can only be filled from TED/gnews; verticals thin on older TED/gnews content
  just get a lopsided mix rather than a forced/padded one.
- Every run: 8,400 selected, 0 verticals needed backfill from blocklisted
  (rejected) articles — the 600 cap and available volume were compatible
  everywhere without relaxing the filter.
- **Real cost at 600/vertical: ~13.86M tokens** (8,400 × ~1,650/call) — still
  above a stricter <10M target, since ~1,450 of those tokens/call is the fixed
  taxonomy block, not something article-count reduction touches. Accepted as
  good enough for now rather than cutting the taxonomy prompt itself.

## Pre-filters tried (2026-08-22) — only 2b (blocklist) is used

Three zero/low-token pre-filter approaches were backtested against the labeled
`article_classifications` data (2,992 rows) before picking one:

- **2b, keyword blocklist** (`prefilter_blocklist.py`) — reject known no-tech
  categories/patterns (e.g. "insurance services", "road salt", "PMI",
  "celebrates") **unless** a tech keyword is present (escape hatch always
  wins). **Used.** Cuts 10.1% of no_match, loses only 0.6% of good articles
  (3/537) — safe, conservative, grounded in real observed no_match examples.
- **2a, keyword whitelist** (`prefilter_whitelist.py`, built but not used) —
  keep only if a tech keyword is present. Backtested: cuts 92.1% of no_match
  but **destroys 66.9% of good articles** (359/537) — real matches often use
  specific product/company names or non-English terms ("Symbotic fulfillment
  system," "SAP BTP," "Frigos connectés") that a generic keyword list can't
  anticipate. Combining with 2b doesn't help — 2b's own escape hatch already
  defers to the same keyword check, so `2a AND 2b` collapses to just 2a's
  (bad) decision. Left in the repo for reference but not wired into
  `select_corpus.py`.
- **2c, local TF-IDF/cosine similarity** (`prefilter_similarity.py`, built but
  not used) — score articles against the 48 taxonomy definitions, no API
  calls. Backtested: score distributions for good vs. no_match articles
  overlap almost completely (medians 0.19-0.24 across all groups) — a full
  threshold sweep showed "good article lost" tracking ~1:1 with "no_match cut"
  at every threshold, i.e. no better than a random cut. Confirmed this isn't a
  non-English-TED artifact (same poor separation on English-only RSS). Pure
  bag-of-words similarity against abstract taxonomy definition text doesn't
  discriminate on this real, messy corpus, despite working fine on clean
  hand-picked example sentences.

## Performance tuning (2026-08-22)

Default settings were far slower and more expensive than necessary:
- **Structured output (`json_schema` response format) isn't reliably honored**
  by this gateway for glm-5.1 — it silently ignores the schema and can return
  free-form text. Don't rely on it; the classifier parses prompted JSON with
  markdown-fence stripping and a retry-once policy instead.
- **Default reasoning effort was the main cost/latency driver**: ~742 output
  tokens and ~9.7s latency per call, most of it hidden reasoning never shown in
  the answer. Setting `reasoning={"effort": "none"}` cut that to ~50-100 output
  tokens and ~2-4s latency, with **no measured quality loss** — tested by
  re-running identical borderline articles under both settings; the model's
  output on ambiguous content is inherently stochastic run-to-run regardless of
  reasoning effort, so effort level isn't the thing driving confidence/quality
  on hard cases.
- **Concurrency**: measured safe ceiling is `MAX_WORKERS = 10` (12+ triggers
  majority `RateLimitError: burst_limit_exceeded`). Combined with the reasoning
  change, effective throughput went from ~0.4-0.5 articles/s to ~1.4+/s — the
  15,283-article full run went from an estimated ~8.5 hours to a projected
  ~2.5-3 hours.
- Retries with exponential backoff (`MAX_TRANSIENT_RETRIES = 6`) absorb the
  occasional 429 at 10 workers without failing the run.

## Token usage

Each call now costs roughly **1,500-1,800 total tokens** (mostly input: the
full 48-entry taxonomy is re-sent on every call, ~1,450 tokens by itself).
Tracked per-row in `article_classifications.tokens_used` (NULL on the small
number of rows classified before tracking was added) and summed at the end of
every run's log output. For the full 15,283-article corpus this would be
roughly 23-27M tokens; for the 8,400-article pool actually used (see "Corpus
selection" below), roughly **13.86M tokens**. No pricing info available for
`https://api.navy`, so $ cost is unknown; ask if you have NavyAI's pricing and
want that computed.

## Output

- `article_classifications` — one row per article: `use_case_id`,
  `technology_id`, `confidence`, `evidence`, `status`
  (`classified`/`no_match`/`needs_review`), `tokens_used`, plus
  `client_relevance`/`client_relevance_reason`/`client_context_ref` when a
  client-context file was used.
  - `no_match`: model correctly found nothing in the taxonomy fits (both ids
    null) — this is a legitimate result, not a failure.
  - `needs_review`: either malformed JSON / invalid id twice in a row, or a
    proposed match with confidence below 0.5 — genuinely ambiguous content,
    flagged rather than force-classified.
  - Signal type, on the same row and from the same single call:
    `signal_type` (one of the six slugs in `common/signal_types.py`),
    `signal_type_confidence`, `signal_date`, `event_date`,
    `event_date_precision`, `signal_type_rationale`, and
    `signal_type_assigned_by` (`deterministic` for TED/OCDS/CORDIS/SAM.gov,
    `llm` for RSS). A response whose `signal_type` fails the enum after retry
    leaves the column NULL and is logged — never coerced to a plausible value.
- `opportunity_spaces` — one row per `(vertical, use_case_id, technology_id)`
  triple with at least one `status='classified'` article: `article_count`,
  `linked_article_ids` (JSON array), `avg_client_relevance` (when active),
  `first_seen_at`/`last_updated_at`. Only rows where **both** use_case_id and
  technology_id are non-null form a real triple; partial matches don't
  aggregate into a space but stay in `article_classifications` for reference.
  - Time horizon, recomputed with the space: `horizon` (`Now`/`Next`/`Later`),
    `horizon_rule` (which rule fired), `horizon_reason`, and the counts the
    rules acted on — `horizon_now_count`, `horizon_next_count`,
    `horizon_later_count`, `horizon_distinct_sources`, `horizon_gated_count`,
    `horizon_out_of_window_count`, `horizon_untyped_count`. Horizon reads only
    signal types, dates, source identities and per-signal confidences; it never
    reads the attractiveness score or any volume proxy.

Read directly from SQLite — no JSON export (user's choice; revisit if a
downstream consumer specifically needs one).

## Client-specific context (optional)

Pass `--client-context path/to/file.md` to inject that file's content into
every prompt as a clearly-separated "CLIENT CONTEXT" block. The model may use
it to judge relevance but the closed-vocabulary contract stays intact — no new
ids, no forced matches. When active, each row also gets `client_relevance`
(0-1) + a one-line reason, and `opportunity_spaces.avg_client_relevance`
aggregates it per space. The file's name is stored as `client_context_ref` for
traceability. Runs without `--client-context` are unaffected.

## Known limitations

- Confidence threshold (0.5) and reasoning effort are constants in
  `collector/client.py`, not CLI flags yet.
- No formal test-mode sampling feature — `--limit N` covers the same practical
  need (validate on a small batch before a full run).
- TED notices are often non-English (French/German/Polish/Norwegian, etc.) —
  the model classifies cross-lingually with generally lower confidence, which
  is exactly why the `needs_review` safety net matters most there.
