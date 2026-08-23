# TED Collector — Innovation Radar Phase 1 (continued)

Queries the TED (Tenders Electronic Daily) Search API once per vertical, using the
CPV / main-activity / keyword mapping in `config/mapping.yaml`, and stores results in
the same `../data/articles.db` table the RSS module writes to (`source_type="ted"`).

## Run manually

```
pip install -r ../requirements.txt
python -m ted_collector.collector.main
```

Run from the repo root (`Pipeline Opportunity/`) — same reason as the RSS module,
the shared `common` package needs to be importable.

## How it queries TED

- **Three requests per vertical**, not one — a single recency-sorted query only ever
  surfaces the last few days for high-volume CPV codes, so instead each vertical's
  250-notice budget is split across three time buckets:
  - **~50% (125) currently active** — `scope=ACTIVE`, no date filter
  - **~25% (63) from ~1 year ago** — `scope=ALL`, `publication-date<=` a cutoff 365
    days back
  - **~25% (62) from ~5 years ago** — `scope=ALL`, `publication-date<=` a cutoff
    1825 days back
  - All three sorted `publication-date DESC`, so each bucket naturally returns
    whatever's closest to (just before) its cutoff — no fixed window, so a
    low-volume vertical still gets a full bucket instead of coming back thin.
- Every CPV code, main-activity code, and keyword in a vertical's mapping entry is
  OR'd together into the base query shared by all three requests.
- Retries on HTTP 429 (rate limit) with exponential backoff, honoring `Retry-After`
  if TED sends one — the 3x request volume per vertical made this necessary; without
  it, 2 of 14 verticals hit the rate limit mid-run.
- No API key required.

## Output

Same `articles` table as the RSS module, plus two columns TED actually uses:
- `confidence` — High / Medium-High / Medium / Low-Medium / Low, exactly as given in
  the vertical mapping table (not filtered out, just tagged — decide how much to
  trust each row downstream).
- `extra` — JSON blob with TED-specific detail not worth promoting to shared columns:
  CPV codes matched, main-activity, buyer country, notice type, total value, deadline.
- `guid` = TED's `publication-number` (the real dedup key — TED notices don't have one
  clean canonical URL the way RSS articles do).
- `url` — best-effort English HTML link extracted from TED's per-language `links`
  object, falls back to another language if English isn't present.

## Dedup

By `guid` (publication-number). Safe to re-run on a schedule — previously-seen
notices are skipped.

## Known limitations (see `../dark_corner.md` for the running list)

- CPV codes are broad/hierarchical, not exact-match — Aerospace and Media &
  Entertainment in particular return heavy overlap with other verticals or noise
  outside the vertical (confirmed with real numbers in `dark_corner.md`).
- `deadline` field is populated on <15% of notices — mostly because `scope=ALL`
  includes awarded notices that never had one.
- Multi-lot notices: TED returns arrays (one entry per lot) for `buyer-country`,
  `classification-cpv`, `main-activity`. This module keeps one row per notice and
  takes the first/English value — lot-level detail is not preserved.

## Scheduling

Same approach as the RSS module — OS-level (Windows Task Scheduler), not built into
the script:

```
schtasks /create /tn "InnovationRadar TED Collector" /tr "python -m ted_collector.collector.main" ^
  /sc daily /st 06:00 /sd 01/01/2026
```
(set "Start in" to the repo root)
