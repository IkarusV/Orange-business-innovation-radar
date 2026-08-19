# Change Record

## 2026-08-19 - `rss_parser.py` metadata-aware RSS collection

### Changed

- Changed the collection output from `rss_digest.csv` to `rss_digest_v2.csv`.
  - The original digest remains unchanged because its header does not contain the new metadata columns.
- Added these columns to every newly collected raw article:
  - `collection_method`
  - `vertical_scope`
  - `signal_types`
  - `language`
- Updated source-registry validation to require the same four columns.
- Limited this collector to active sources whose `collection_method` is `rss`.
  - Other future source methods, such as API, portal, or manual collection, are ignored by this RSS-specific script.
- Added validation for active RSS sources. The parser now reports a clear error if `source`, `feed_url`, `vertical_scope`, `signal_types`, or `language` is blank.
- Copied the source metadata into the in-memory source record and each output article record.

### Required registry migration

`source_registry.csv` must add the following columns before this parser can run:

```csv
collection_method,vertical_scope,signal_types,language
```

For this script, active feed rows must set `collection_method` to `rss`. Example values are `manufacturing`, `cross_industry`, `proof|market_move`, and `en`.

## 2026-08-19 - `source_registry.csv` metadata migration

### Changed

- Added four columns to the original seven-column source registry:
  - `collection_method`
  - `vertical_scope`
  - `signal_types`
  - `language`
- Set `collection_method` to `rss` for all 31 existing active feed sources.
- Set `language` to `en` for all existing English-language feeds.
- Added `vertical_scope` as a source-level collection hint.
  - Manufacturing-specific sources are marked `manufacturing`.
  - Broad technology and business feeds are marked `cross_industry`.
  - Sector-specific sources retain an appropriate sector hint, such as `healthcare`, `energy`, or `retail`.
- Added pipe-separated `signal_types` hints based on each source's usual coverage, such as `proof|market_move` or `regulation|buying|proof|market_move`.

### Preserved

- All original source names and feed URLs.
- Source categories, quality defaults, independence groups, and domains.
- Active status for every source.

### Interpretation

`vertical_scope` and `signal_types` are source metadata only. They guide collection coverage and later triage; they do not classify every article from a source as belonging to that vertical or signal type.

## 2026-08-19 - Market Intelligence data templates

### Changed

- Created `market_intelligence_data/manufacturing_coverage_matrix.csv`.
  - Records manufacturing source availability and known evidence gaps by signal type.
  - Source availability is a coverage indicator, not a claim that every raw article has that signal type.
- Created `market_intelligence_data/triage_results.csv`.
  - Defines the persisted Stage 1 article-triage schema, including raw-article linkage, source context, canonical taxonomy IDs, rationale, model/prompt version, and review state.
- Created `market_intelligence_data/evidence_records.csv`.
  - Defines the later evidence-claim schema, including excerpt, canonical taxonomy IDs, organizations, dates, source context, label status, and review fields.
- Moved the three files from the repository root into `market_intelligence_data/` to separate derived Market Intelligence datasets from collection scripts, raw RSS snapshots, and taxonomy dictionaries.

## 2026-08-19 - Taxonomy and Market Intelligence data mechanism

### Taxonomy role

The `taxonomy/` folder is the controlled reference vocabulary. Its files define allowed labels; they do not contain collected evidence or calculated scores.

- `verticals.csv` defines the customer industry, currently the approved `manufacturing` MVP vertical.
- `use_cases.csv` defines concrete customer needs and links each use case to its allowed `vertical_id`.
- `technologies.csv` defines technical approaches that may enable a use case.
- `signal_types.csv` defines the type of external evidence: `regulation`, `buying`, `proof`, `maturity`, `market_move`, or `market_trend`.
- `synonym_map.csv` maps alternate wording, such as `IIoT`, to a canonical taxonomy ID. It prevents equivalent terms from creating separate opportunity clusters.

Only rows with `status=approved` are loaded by `triage_articles.py`. This prevents unreviewed labels from becoming stored classifications.

### Market Intelligence data role

The `market_intelligence_data/` folder stores pipeline outputs and coverage monitoring rather than controlled vocabulary.

- `manufacturing_coverage_matrix.csv` tracks whether the source portfolio covers each manufacturing signal type and identifies collection gaps. It is a source-coverage view, not article-level classification.
- `triage_results.csv` stores one Stage 1 relevance decision per raw RSS article. Each row links back to the immutable raw article using `article_guid` and `article_link`.
- `evidence_records.csv` will store zero, one, or multiple source-supported claims from each relevant article. Each claim remains linked to its source article through `article_guid`.

### Data flow

```text
source_registry.csv
    -> rss_modi_parser.py
    -> rss_digest_v2.csv (immutable raw article records)
    -> triage_articles.py
    -> market_intelligence_data/triage_results.csv
    -> evidence extraction
    -> market_intelligence_data/evidence_records.csv
    -> event deduplication and opportunity clustering
    -> deterministic scoring and Radar/Watchlist publication
```

`vertical_scope` and `signal_types` in `source_registry.csv` are source-level hints only. `triage_articles.py` must classify each article from its actual content, then validate any returned taxonomy IDs against the approved taxonomy files.

### Current triage-script state

`triage_articles.py` already loads approved taxonomy IDs, skips previously processed article GUIDs, validates returned labels, and appends traceable rows to `triage_results.csv`.

The `classify_article()` function is intentionally not yet implemented because it requires a selected AI provider and authenticated model call. Until that function is connected, the script cannot produce triage classifications. `synonym_map.csv` is also not yet loaded by the script; it will be used during normalization when the classifier produces alternate wording rather than canonical IDs.

## 2026-08-19 - Manual manufacturing triage pilot

### Changed

- Added 30 manually triaged records to `market_intelligence_data/triage_results.csv`.
- The pilot used 20 Automotive World records and 10 Manufacturing Dive records from `rss_digest_v2.csv`.
- All results use `prompt_version=1.0-manual-pilot`, `model=gpt-5.6-terra`, and `review_status=pending_review`.

### Results

- 11 records were classified `RELEVANT`.
- 19 records were classified `IRRELEVANT`.
- Relevant records by primary signal type: 6 `market_move`, 3 `proof`, 1 `buying`, and 1 `maturity`.
- No record was published, scored, or converted into an evidence record.

### Observations

- The Automotive World source contains substantial consumer-vehicle content, so source-level `vertical_scope=manufacturing` must not be treated as article-level classification.
- Several relevant market events did not map to an approved manufacturing use case or technology. The fields were intentionally left blank rather than inventing a taxonomy label.
- `triage_articles.py` currently accepts `IRRELEVANT`, while the original triage prompt says `NOT_RELEVANT`. Future automated implementation should standardize this vocabulary before execution.

## 2026-08-19 - RSS collector rename

### Changed

- Renamed `rss_parser.py` to `rss_modi_parser.py`.
- Updated the active collector reference in `Alec_steps.md`.
- Updated the current pipeline diagram in this change record.

### Preserved

- Collection behavior, source-registry validation, and output path (`rss_digest_v2.csv`) are unchanged.
- `triage_articles.py` requires no update because it reads the digest file directly and does not import the collector module.
