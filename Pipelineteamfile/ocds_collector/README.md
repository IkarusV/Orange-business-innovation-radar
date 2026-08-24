# OCDS Collector — Innovation Radar Phase 1 (continued)

Queries three OCDS-standard public procurement sources — **UK** (Find a Tender +
Contracts Finder), **Ukraine** (ProZorro) — using the CPV mapping in
`config/mapping.yaml` (reused from `ted_collector/config/mapping.yaml`), and
stores results in the same `../data/articles.db` `articles` table the RSS/TED
modules write to (`source_type="ocds_uk"` / `"ocds_ua"`).

**Australia (AusTender) is not queried** - no live API was found. See "Australia"
below.

## Run manually

```
pip install -r ../requirements.txt
python -m ocds_collector.collector.main
```

Run from the repo root (`Pipeline Opportunity/`), same reason as every other
collector module - the shared `common` package needs to be importable.

## How it queries each source (all verified live, 2026-08-22)

### UK: Find a Tender (FTS) + Contracts Finder (CF)

Both are free, unauthenticated OCDS `releasePackages` APIs published by the
Cabinet Office:
- FTS: `https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages`
- CF: `https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search`

**Neither supports server-side CPV filtering** - confirmed live, not assumed:
- FTS's only accepted query params are `stages`, `limit`, `cursor`,
  `updatedFrom`, `updatedTo` (confirmed via its own 400 error message listing
  allowed params). No CPV/classification param exists.
- CF *does* accept a `cpvCodes` param, but it's a silent no-op: a request with
  `cpvCodes=33000000` and the same request with no `cpvCodes` at all returned
  byte-identical release lists in testing. CF also doesn't validate unknown
  param names (a `bogusparam=1` test also returned 200), so this isn't
  something a 400 error would ever reveal - had to compare result sets
  directly to catch it.

So CPV matching happens **client-side**: page through releases (`limit=100`,
the server-enforced max on both), extract every CPV code attached anywhere on
a release (`tender.classification`, `tender.items[]`, `awards[].items[]`,
both `.classification` and `.additionalClassifications`), and keep releases
where any code's **division** (first 2 digits) matches the vertical's mapped
CPV list - same broad/hierarchical match TED's own README already flags, now
also standing in for a filter neither UK endpoint actually offers.

**Three time buckets per vertical, 250 total, split 50/25/25** (same shape as
TED): `recent` (no date filter), `1y_ago` (`updatedTo`/`publishedTo` cutoff
~365 days back), `5y_ago` (cutoff ~1825 days back) - always
`date<=cutoff` sorted newest-first via the API's own cursor pagination, never
a fixed window (confirmed: both endpoints return strictly newest-first up to
the cutoff). Each bucket's target is split 50/50 between FTS and CF, each
scanning up to 5 pages (500 releases) before giving up on a thin vertical.

FTS launched Jan/Feb 2021, so `5y_ago` (cutoff ~2021-08) sits right at its
data horizon - confirmed live it returns real (if sparser) data there, not
empty.

### Ukraine: ProZorro

Free, unauthenticated: `https://public.api.openprocurement.org/api/2.5/tenders`.

The list endpoint is a **changes feed** - each entry is just `{id,
dateModified}`, nothing else. `opt_fields` (ProZorro's documented field-expansion
param) is a confirmed no-op on this deployment - classification only exists on
the full per-tender `GET .../tenders/{id}`, so every candidate costs a second
request. Total budget per vertical is deliberately smaller than UK/TED because
of that (60, not 250) - a cost tradeoff, not thinner underlying data.

`descending=1` + `offset=<ISO cutoff>` reliably jumps into the feed at (and
before) a given timestamp, still sorted newest-first from there - verified
live this is a real cutoff, not ignored (results jumped cleanly from 2026 to
2021 when tested). Same `date<=cutoff` sorted DESC pattern as UK/TED, no fixed
window. Each bucket detail-fetches up to 60 candidates before giving up on a
thin vertical.

**CPV deviation, confirmed live (this is the thing the brief asked to check,
not assume):** ProZorro's classification *scheme label* is not stable "CPV".
A 2015-era tender used `scheme: "CPV"` with a CPV-format id (`"14410000-8"`).
Current (2026) tenders instead use `scheme: "ДК021"` - Ukraine's own name for
its national CPV adaptation - with the same CPV-format id (e.g. `"03220000-9"`,
a real CPV code for produce). Same code space either way, so both scheme
labels are accepted (`extract_ua_cpv_codes()` in `collector/query.py`). Also
confirmed: `items[].additionalClassifications` on ProZorro is a *different*
taxonomy (ДКПП, product-by-economic-activity) and is deliberately not scanned
for CPV matches - only `items[].classification` and the rarer top-level
`tender.classification` carry CPV/ДК021.

Retries on HTTP 429/5xx with exponential backoff on every request (list pages
and per-tender detail fetches alike) - normal for a public institutional API
under this module's request volume, same reasoning as `ted_collector`.

### Australia: not queried (no live API found)

Checked live, not assumed:
- `www.tenders.gov.au` (AusTender) sits behind a CloudFront bot-block - plain
  requests 403 outright; even with a full browser User-Agent, every guessed
  `/api/Atm/*`, `/swagger`, `/api/help` route returned a proper ASP.NET-style
  404 ("No HTTP resource was found...") rather than real data - i.e. *some*
  API surface exists behind that hostname, but no documented, guessable, or
  discoverable public search endpoint was found.
- `data.gov.au` confirms what AusTender's actual bulk-data product is: a
  weekly CSV **file** ("Contract Notice Export", dataset id
  `austender-contract-notice-export`), not a query API.

Per explicit instruction: no scraper, no external UNSPSC codeset research.
Australia contributes **0 rows** this run - `countries.au.enabled: false` in
`config/mapping.yaml`, with the reasoning and the 3 pre-confirmed UNSPSC
segments (43 = IT/Broadcasting/Telecoms → Media & Entertainment; 81 =
Engineering/R&D/Tech Services → cross-cutting; 80 = Management/Business
Professional Services → Public/Gov sector) kept there as reference in case a
live API surfaces later. Every other vertical would stay unmapped for
Australia even then - not guessed at.

## Output

Same `articles` table as RSS/TED:
- `confidence` - flat `"good"` for every OCDS row, same convention as
  RSS/TED (not a noise filter - see `dark_corner.md`/project memory for why).
- `extra` - JSON blob: matched CPV codes, buyer name, buyer country, stage/
  status, value + currency; UK rows also carry `sub_source`
  (`"fts"`/`"contracts_finder"`) and `ocid`; UA rows carry
  `procurement_method_type` and the human-readable `tender_id`.
- `time_window` - `recent` / `1y_ago` / `5y_ago`, always via a cutoff query
  sorted descending, never a fixed date window.
- `guid` - `UK-FTS-{release id}` / `UK-CF-{release id}` /
  `UA-PROZORRO-{tender id}` - the real dedup key, same reasoning as TED's
  `publication-number` (OCDS notices don't have one universally-clean URL).
- `url` - FTS: constructed as `find-tender.service.gov.uk/Notice/{id}`
  (verified live for both tender- and award-stage releases). CF: extracted
  from the release's own `documents[].url` (no reliable construction rule
  found for CF's id format). UA: constructed as
  `prozorro.gov.ua/tender/{tenderID}` (the human-readable ID, not the
  internal hash).

## Dedup

By `guid` (and `url` where present), same `INSERT OR IGNORE` mechanism as
every other module. Safe to re-run on a schedule.

## Known limitations

- **CPV/ДК021 matching is client-side and division-level (broad), not
  exact** for all three live sources - neither UK endpoint nor ProZorro
  offers a real classification filter, so this module scans and filters
  itself rather than asking the API to. Same overlap/noise caveat TED's
  README already documents for CPV in general, now doubly true since nothing
  here pre-filters before the division check.
- **Thin verticals are expected, not bugs.** UK: capped at 5 pages
  (500 releases) scanned per bucket per sub-source - a vertical whose CPV
  division is rare (e.g. Public/Gov sector, CPV 75, returned well under target
  in testing) comes back thin rather than the module scanning indefinitely.
  Ukraine: capped at 60 detail-fetched candidates per bucket, same reasoning,
  compounded by the N+1 request cost.
- **Ukraine's total budget (60/vertical) is intentionally smaller than
  UK/TED (250/vertical)** - purely a cost tradeoff forced by ProZorro's
  changes-feed design (no field expansion, so CPV requires a second request
  per candidate), not a statement about data quality or availability.
- **Contracts Finder's `cpvCodes` param looking like a real filter but being
  a no-op** is the kind of thing that would silently produce wrong results if
  trusted without a live comparison - worth remembering if CF's API ever gets
  revisited.
- Australia: 0 rows, by design - see above.

## Scheduling

Same approach as every other module - OS-level (Windows Task Scheduler), not
built into the script:

```
schtasks /create /tn "InnovationRadar OCDS Collector" /tr "python -m ocds_collector.collector.main" ^
  /sc daily /st 06:30 /sd 01/01/2026
```
(set "Start in" to the repo root)
