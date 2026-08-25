# Pipeline Opportunity export → Innovation Radar V2 bootstrap

Exported **2026-08-25** from the standalone, already-completed Innovation Radar run at
`C:\Users\danuk\OneDrive\Pipeline Opportunity` (source DB:
`C:\Users\danuk\OneDrive\Pipeline Opportunity\data\articles.db`). The source project was
read-only throughout — nothing there was modified.

## What is in this folder

| File | Contents |
| --- | --- |
| `opportunity_spaces.json` | All **309** opportunity spaces, with `use_case_id` / `technology_id` resolved to human-readable labels via `Pipelineteamfile/opportunity_classifier/config/taxonomy.json` (identical taxonomy in both projects). Includes `linked_article_ids`, `article_count`, `first_seen_at`, `last_updated_at`. |
| `opportunity_spaces.csv` | Same 309 rows, flat, for quick scanning in a spreadsheet. |
| `articles.json` | The **548** distinct linked article records behind those spaces, keyed by their source `articles.id` — title, url, guid, source_name, source_type, vertical, published_date, summary, collected_at, confidence, extra, time_window. |
| `manifest.json` | Export counts and breakdowns (spaces per vertical, source types, distinct use cases / technologies). |
| `loaded_selection.json` | Exactly which spaces and articles were picked to seed the live app (see below). |

Source coverage of the 309 spaces: 14 verticals, 25 distinct use cases, 18 distinct
technologies. Linked-article source mix: cordis 315, gnews 121, rss 52, ted 48,
ocds_uk 11, ocds_ua 1.

## What was loaded into the live app

The app's team database (`Pipelineteamfile/data/articles.db`) did not exist before this
run. Rather than copy Project A's already-computed labels — which would have cost nothing
and loaded nothing new — **raw, unlabelled articles** were inserted at the app's own team
articles boundary and put through the app's own live pipeline:

1. **Selection** — 30 target spaces chosen round-robin across all 14 verticals, one
   distinct `(use_case_id, technology_id)` pair each, ordered by source `article_count`.
   `gnews` articles were excluded because `select_corpus.py` never pools that source.
   → **41 candidate articles** (1 article per space, 2 for spaces with >= 5 source articles).
2. **Insert** — via `common.storage.get_connection` + `insert_articles`, creating the team
   DB and schema. 41/41 inserted (no dedup collisions).
3. **Corpus selection** — `opportunity_classifier.collector.select_corpus.run()` (offline,
   free). All 41 passed the blocklist → pool of 41.
4. **Classification** — `opportunity_classifier.collector.main.run(limit=N)` in four small
   batches (8, 10, 10, 6) against the **real Navy API**
   (`NAVY_MODEL=gpt-5.6-luna`, key read from the repo-root `.env`, which was not modified).
   Stopped as soon as the opportunity-space count passed 20; **7 pooled articles were
   deliberately left unclassified** to avoid unnecessary spend.

### Results

| Metric | Value |
| --- | --- |
| Articles inserted into the team DB | **41** |
| Articles actually classified (real API calls) | **34** |
| Classification outcomes | 32 `classified`, 1 `needs_review`, 1 `no_match` |
| Distinct opportunity spaces now live | **21** |
| Verticals represented | 13 of 14 |
| **Total Navy tokens spent** | **56,027** |
| Tokens per call | min 1,506 / avg 1,648 / max 3,101 |

The 21 spaces are Project B's **own** classifier output, not a copy of Project A's labels —
the two runs do not always agree, which is why the candidate set was oversampled.

Token figure is authoritative, taken from the fresh team DB:
`SELECT SUM(tokens_used), COUNT(*) FROM article_classifications` → `(56027, 34)`.

### Verified in the running app

Checked with headless Chromium against the live dev server (server left running, never
restarted):

- `http://localhost:3030` — stat cards read **21 Opportunity spaces**, **41 Market
  signals**, **14 Sectors covered**, **1 Needs attention**. The demo fallback values
  (4 / 52 / 4 / 7) are gone. Source coverage panel shows EU research programmes 30,
  Rss 10, European procurement 1.
- `http://localhost:3030/opportunities` — 21 real cards across Defense, Healthcare,
  Aerospace, Automotive, Energy, Finance/Banking/Insurance, Manufacturing, Natural
  Resources, Public/Gov sector, Retail, Transportation & Construction, Lifesciences and
  Media & Entertainment. None of the four hardcoded demo entries appear.
- `http://localhost:3030/opportunities/3` — detail page renders the real CORDIS evidence
  records behind the Defense / Compliance monitoring / Cybersecurity Platform space,
  with genuine titles, dates and per-article confidences.

`radar_v2.services.team_repository.database_ready()` returns `True`.

## Reproducing / extending

The helper that did the seeding is `Pipelineteamfile/_import_run.py`:

```
.venv\Scripts\python.exe Pipelineteamfile\_import_run.py select      # pick, insert, pool
.venv\Scripts\python.exe Pipelineteamfile\_import_run.py classify 8  # one paid batch
.venv\Scripts\python.exe Pipelineteamfile\_import_run.py status      # counts + token spend
```

`classify` is the only command that costs money. It skips anything already in
`article_classifications`, so re-running it never re-pays for an article. 7 pooled
articles remain unclassified if more spaces are ever wanted.
