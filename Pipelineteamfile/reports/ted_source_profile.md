# TED Source Profile — reference for finding similar sources

Written 2026-08-22. Purpose: the user is moving toward a more TED-centric
source mix (away from gnews, which was paused for reliability reasons — see
`dark_corner.md`). This document captures what TED actually is, how this
pipeline uses it, and — most importantly — **what structural properties made
it valuable**, so a similar source can be identified by matching those
properties rather than by superficial similarity ("another government site").

## What TED is

Tenders Electronic Daily — the EU's official, centralized public procurement
notice database. Every EU member state (and some EEA/candidate countries)
publishes government and public-sector purchasing notices there: what's being
bought, by whom, for how much, and under what classification. Free, public,
no API key, no paywall.

## API mechanics (for replicating the pattern against a candidate source)

- Endpoint: `POST https://api.ted.europa.eu/v3/notices/search`, JSON in/out.
- "Expert query" syntax: `field=value`, `field IN (...)`, `AND`/`OR`, date
  comparisons (`>=`/`<=`), `SORT BY field DESC`. No official public docs for
  this syntax — pieced together from community examples and verified live
  before trusting it (see `ted_collector/README.md` for the verification
  history).
- `limit` max 250/page. `scope=ACTIVE` (currently open notices) or
  `scope=ALL` (includes historical/awarded).
- No pagination beyond page limits was used in practice — instead, time
  bucketing (see below) controls volume.

## How this pipeline queries it (`ted_collector/`)

One vertical at a time (14 verticals), **3 requests per vertical**:
1. Currently-active notices (`scope=ACTIVE`, no date filter)
2. Notices published before a cutoff ~1 year back (`scope=ALL`,
   `publication-date<=cutoff`, sorted DESC — a plain cutoff, not a fixed
   window, so low-volume verticals still fill their bucket)
3. Notices before a cutoff ~5 years back (same mechanism)

Each request's `query` OR-combines that vertical's **CPV codes** (the EU's
standard hierarchical procurement classification — e.g. `09000000` =
"energy", `34000000` = "transport equipment"), **buyer main-activity codes**
(e.g. `defence`, `health`, `electricity`), and a handful of free-text
keywords, all defined in `ted_collector/config/mapping.yaml`.

## Fields extracted, mapped to the shared `articles` schema

| TED field | maps to |
|---|---|
| `publication-number` | `guid` (dedup key — TED has no single canonical URL, this is used instead) |
| `notice-title` (multilingual dict) | `title` (English key if present, else first available language) |
| `publication-date` | `published_date` |
| buyer name / country / notice-type / value | synthesized into `summary` |
| `classification-cpv`, `main-activity`, `deadline`, `total-value` | stored in an `extra` JSON column |

Notice titles are structured `Country – Category – local-language details` —
**the Category segment is always in English**, even when the rest of the
notice is in French/German/Polish/etc. This is TED's own classification
label, not a translation, and it's a real (partial) mitigation for the
multilingual-content problem documented elsewhere in this repo.

## Why TED worked well here — the properties to look for in a similar source

1. **Institutional/official signal, not commentary.** A procurement notice is
   direct first-party evidence that a real organization is buying a real
   technology or service — closer to ground truth than a news article
   discussing a trend. This is qualitatively different from RSS/gnews, which
   report *about* things rather than *being* the transactional record.
2. **Free and unauthenticated.** No API key, no payment tier, no rate limit
   tied to a subscription.
3. **Has a real classification taxonomy**, not just free text — CPV codes
   gave this pipeline something to query against directly (`classification-
   cpv=09000000`) rather than relying on keyword search alone. A candidate
   source with its own structured category/classification system is much
   easier to map onto the Vertical × Use Case × Technology taxonomy than one
   with only free-text descriptions.
4. **Genuine historical depth**, reliably queryable. RSS is recency-only by
   construction (feeds only carry current items); gnews's historical reach
   was inconsistent and inferior to TED's. TED let us reliably pull notices
   from exactly ~1 year or ~5 years back.
5. **Broad institutional coverage** — all 27 EU member states in one API,
   rather than needing 27 separate integrations.

## Known weaknesses (also worth checking a candidate source against)

- **CPV codes are hierarchical/broad, not exact-match** — caused real
  cross-vertical noise (e.g. Aerospace and Automotive share CPV `34000000`;
  Aerospace's TED data was consequently the weakest in the corpus). A
  candidate source's classification system should be checked for how
  cleanly its categories map to a single vertical before trusting it.
- **Multilingual**: only ~41% of TED notices detected as English (2,191 of
  5,350). A candidate source that's single-language would avoid this
  entirely; a multilingual one would inherit the same problem.
- **Rate limiting and transient errors**: occasional HTTP 429 (burst limit)
  and 521 (origin down) responses — needed retry-with-backoff. Not unusual
  for a public institutional API; budget for it.

## Scale and value delivered

5,350 articles collected. Of the ~5,045 later sent to the LLM classifier,
824 were confirmed real matches (16.3% positive rate) — the richest
confirmed-signal source in the corpus by volume, ahead of RSS's 30.6%
*rate* but much larger absolute count. TED notices form a large share of the
real opportunity-space findings in `reports/opportunity_spaces_2026-08-22.pdf`.

## What a "similar source" search should look for

A source that is: (a) an official/institutional/first-party record (not
news/commentary), (b) freely and publicly queryable without payment, (c)
organized under its own structured classification system that could
plausibly map to Vertical × Use Case × Technology, (d) capable of genuine
historical lookback, not just a live feed. Examples of the *category* worth
searching (not vetted, just the shape): other countries'/blocs' public
procurement registers (e.g. US SAM.gov, UK Find a Tender), grant/funding
award databases, regulatory approval/registration databases, patent
filings, standards-body registries — anything where an official body
records a real transaction or decision, not a publisher's article about one.
