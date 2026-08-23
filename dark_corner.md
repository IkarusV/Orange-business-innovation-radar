# Dark Corner — verticals/domains not well covered by RSS or TED

Running list of gaps in automated coverage, to route to AI agent search (Phase 3) or
flag as a manual-watch item. Add to this as TED coverage gets built out.

**2026-08-22: pipeline going TED-centric.** `rss_collector/` and
`gnews_collector/` code were both deleted (backup kept outside the repo, not
in version control since this isn't a git repo) — the collected data from
both (747 rss, 9,186 gnews articles) stays in `data/articles.db` untouched,
just no more collection happens. gnews was paused first for reliability
reasons (see the section below); rss was removed at the same time as part of
a deliberate move toward more TED-like sources (official/structured data,
not news aggregation) — see `reports/ted_source_profile.md` for what
properties are being searched for in replacement sources. The RSS-thin-
coverage table below is now historical — it describes gaps in a source that
no longer runs.

## RSS — thin coverage (as of first collection run, 2026-08-21)

| Vertical | Feeds | Articles (first pull) | Note |
|---|---|---|---|
| Retail | 1 (Retail Dive) | 10 | Single source, low volume |
| Wholesale | 1 (Modern Distribution Mgmt) | 20 | Single source |
| Natural Resources | 1 (MINING.com) | 36 | Single source |
| Aerospace | 1 (Defense Daily) | 50 | Single source; feed is really a Defense outlet, not aerospace-specific |
| Media & Entertainment | 2, but TVNewsCheck is blocked (403, Cloudflare) | 15 (effectively 1 working feed: Digiday) | See RSS README known issues |
| Healthcare | 3, but Healthcare IT News is blocked (403, Cloudflare) | 25 (effectively 2 working feeds) | See RSS README known issues |

Everything else (Manufacturing, Finance/Banking/Insurance, Public/Gov, Defense,
Transportation & Construction, Lifesciences, Energy, Automotive) has 2+ working
sources and reasonable volume — not flagged here for now.

## TED — gaps (first full run, 2026-08-21, scope=ALL, 250-notice page cap/vertical)

Confirms the brief's low-confidence warnings with real numbers — "new" count is low
where a vertical's CPV/main-activity codes overlap heavily with another vertical
already queried in the same run (dedup by `publication-number` catches the repeats):

| Vertical | Confidence | Notices fetched | New (not already seen) | Note |
|---|---|---|---|---|
| Aerospace | Low | 250 | 23 | CPV identical to Automotive, main-activity identical to Defense — almost entirely overlap, as flagged. Needs its own CPV code if one exists. |
| Media & Entertainment | Low-Medium | 250 | 94 | CPV 92000000 noise (sport/recreation/culture mixed in) as flagged. |
| Wholesale | Low | 250 | 249 | No overlap issue, but 63100000 (cargo handling) is a weak logistics proxy for wholesale trade — still unresolved from the brief. |
| Retail | Low | 250 | 247 | CPV 55000000 pulling in hospitality/catering as flagged; low overlap with other verticals though. |

Also: `deadline` field is sparse across the board (302/2645 TED rows) — mostly because
`scope=ALL` includes awarded/historical notices that never had one, not a field-name
bug. If a later stage needs deadlines specifically, filtering TED to `scope=ACTIVE`
notice-types would raise that rate.

**Still needs its own vertical-specific CPV research** (per the brief, not done here
without sign-off): Aerospace, Wholesale.

## Google News RSS — added 2026-08-21 to address the RSS gaps above

`gnews_collector` now queries Retail, Automotive, Wholesale, Natural Resources, and
Aerospace (the RSS-thin list above) for recent coverage, plus all 14 verticals for
~1-year-ago and ~5-years-ago historical coverage no curated RSS feed can offer. Not
a replacement for the RSS-thin flag above — a keyword search on Google News is a
different, noisier signal (title-only, no article body, unofficial endpoint) — but
it's a real mitigation, not just a note. See `gnews_collector/README.md`.

New noise pattern to watch, same shape as TED's CPV problem but a different cause:
single-word keyword collisions with unrelated senses. Confirmed live: "wholesale"
pulls in "wholesale inflation" (macroeconomic term) articles alongside genuine
wholesale-trade news; "supply chain" pulled in a NATO fuel-logistics story and a
cybersecurity story. No confidence tagging applied to this source (see
`gnews_collector/README.md` for why) — treat `source_type="gnews"` rows as noisier
than RSS/TED by default, especially for Wholesale.

NavyAI agent search (the original Phase 3 concept — an LLM-driven search agent) is
paused, not resumed and not built. Google News RSS is a separate, non-AI source
that was added instead to cover the same gaps more cheaply.
