# Innovation Radar — Collection Pipeline

Hybrid discovery pipeline maximizing candidate diversity across the Vertical x Domain matrix. Output: deduplicated `raw_signals` in SQLite, ready for the downstream triage/scoring agents.

## Architecture

```
RSS feeds ─────┐
TED API ───────┼──► normalize ──► dedup (guid + canonical URL + near-dup titles) ──► radar.db
NavyAI/Sonar ──┘                                                                        │
     ▲                                                                                  ▼
     └────────────── coverage monitor boosts underrepresented cells ◄── coverage_stats
```

Connectors:
- **rss** — existing feed list (drop your `flux_rss_innovation_radar.md` into `config/`). Tag regulator feeds with `[regulator]` in the line to get source_quality 5 and a `regulation` signal hint.
- **ted** — EU public procurement (buying signals), filtered by CPV prefixes mapped to radar domains in `connectors/ted.py`.
- **navy** — coverage-driven search, **free**: uses your existing NavyAI key against the `sonar` model (Perplexity), which has live web search built in — no separate search API or subscription needed. 14 verticals x 6 domains x 3 signal-type templates = 252 queries per full run, covered by NavyAI's free daily token quota. Cells below `coverage_threshold` get doubled attention (more explicit instruction to widen the search in the prompt).

The `navy` connector prompts Sonar to return a strict JSON array (title, url, published_date, snippet) per query; since Sonar doesn't support JSON mode, parsing is done with a regex extraction + `json.loads`, and malformed responses are silently skipped rather than crashing the run.

## Setup

```
pip install -r requirements.txt
export NAVY_API_KEY=your_key       # https://api.navy — same key used for triage/scoring
```

## Usage

```
python pipeline.py                          # all connectors
python pipeline.py --connectors rss ted     # skip the search connector (no LLM calls)
```

To use a stronger (and costlier) Sonar tier, edit `DEFAULT_MODEL` in `connectors/navy_search.py` — `sonar-pro` gives deeper, more thorough search at higher token cost; `sonar` (default) is the cheapest and stays comfortably inside the free daily quota for a 252-query run.

Each run is incremental: existing guids/URLs are skipped, near-duplicate titles filtered, and a coverage report (least covered cells first) is printed.

## Output schema (`raw_signals`)

| Column | Maps to evidence record |
|---|---|
| source_name, source_type | Source |
| source_quality | Source quality (deterministic, by source type) |
| published_at | Publication date |
| url_canonical | Source URL |
| geography | Geography (native for TED, else null) |
| vertical_hint, domain_hint | Vertical / Technology (pre-fill for triage agent) |
| signal_type_hint | Signal type (pre-fill) |
| title + content | Input for Claim / Use case extraction downstream |

Hints are collection-time metadata, not final labels — the triage agent confirms or overrides them.

## Extending

- EUR-Lex connector (regulation): SPARQL on CELLAR or the EUR-Lex web service, same `make_signal` pattern as `ted.py`.
- EPO OPS connector (technology maturity): free tier, map IPC/CPC codes to domains like CPV codes in `ted.py`.
- Azure deployment: `run()` maps directly to a timer-triggered Function (same pattern as sncblive); swap SQLite for Azure SQL by replacing `db.py`.
- Embedding-based dedup: replace `SequenceMatcher` in `dedup.py` once volume makes cross-language duplicates an issue.
