# Innovation Radar — presentation walkthrough

Local app: **http://localhost:3030** (start with `start.bat`, or `.venv\Scripts\python.exe -m reflex run` from the repo root).

Structured to match how you'll actually present: page by page, in the order they sit in the nav (`/` → `/opportunities` → an opportunity detail → `/company` → the rest). For every number on screen, this tells you exactly where it comes from, so you can answer "how did you get that?" without hesitating. Known gaps are called out explicitly — better to pre-empt those questions than get caught by them live.

---

## The one-sentence pitch

The radar turns raw institutional signals (EU tenders, funded research, procurement notices, market news) into ranked, explainable business opportunities — every number on every page traces back to real data, and any component with insufficient data says so honestly instead of showing a fake zero or a padded number.

---

## Page 1 — Overview (`/`)

The landing dashboard. Four stat tiles, then two charts, then a live sample of the ranked list.

**Stat tiles** (top row):
- **Opportunity spaces** — count of rows in `opportunity_spaces`, i.e. distinct (vertical × use case × technology) clusters the classifier has produced from real evidence.
- **Market signals** — total article count across all connected sources (TED, CORDIS, OCDS, RSS).
- **Sectors covered** — distinct verticals with at least one signal.
- **Needs attention** — classifications the LLM itself flagged `needs_review` (low confidence / ambiguous taxonomy match), i.e. a built-in quality queue, not an arbitrary count.

**"Portfolio pulse" bar chart** — one bar per opportunity space, height = its **Attractiveness score** (see Page 3 for the full breakdown of what that number is).

**"Source coverage" panel** — signal count per source type (TED / CORDIS / OCDS-UK / OCDS-Ukraine), so you can show the evidence base isn't single-sourced.

**"Opportunities gaining momentum"** — the top 3 spaces under whichever **role mode** (Strategist / Sales / Presales) is currently active, sorted by that mode's own sort rule. This is a live preview of Page 2, so mentioning the mode badge here is a good segue.

---

## Page 2 — Opportunities list (`/opportunities`)

This is where you'll spend the most time. Two things happen on this page: **role mode** switching, and **filtering**.

### Role mode switcher (top of page)
Three modes — **Strategist**, **Sales**, **Presales**. Switching mode does three things, and it's worth saying this explicitly since it's the most "designed" part of the app:
1. **Seeds different default filters** (Sales asks for a persona first; the others don't).
2. **Changes the sort order** (Strategist/Presales sort by Attractiveness; Sales sorts by a persona-weighted score — see below).
3. **Changes the recommended move text on every card and detail page** — a Strategist and a Salesperson looking at the *same* opportunity get a different suggested next action.

Mode only changes filters if you haven't touched them yet — once you've customised a filter, switching mode never silently discards your choice.

**Sales mode looks different**: it switches to a single wide card per topic instead of the grid, because the brief was "usable live in front of a customer" — no extra clicks needed to see the recommended move and the top persona.

### Filters
- **Search** — free text across vertical, use case, technology.
- **Vertical / Horizon** — standard single-select dropdowns.
- **Business domains** (chip row) — Orange's 6 internal domains (OX: Smart Industries, Connectivity, Cybersecurity, Cloud, CX, EX). Multi-select, OR within domain, AND against other filters. Derived deterministically from each space's technology + use case (not from an LLM call) — say this if asked, it's a credibility point.
- **Geography** (chip row) — regions derived from real country data (TED buyer country, CORDIS consortium countries, OCDS buyer country; RSS is inferred by the LLM when the text names a place). Selecting "Global / Cross-region" only matches signals explicitly about EU-wide regulation or worldwide statements — it deliberately does **not** also catch topics that simply have no geography tagged; those are a separate, honestly-labelled state.

**Known live gap to mention if asked**: geography is fully filterable here but isn't shown as a badge on the cards or detail page yet (domain is). It's real data, just not surfaced visually past this filter row yet.

### The cards
Each card shows: vertical badge, domain badge, horizon badge (Now/Next/Later), use case, technology, one-line summary, **Attractiveness / 100**, **Momentum**, and **Signal count**. "Open opportunity" goes to Page 3, where everything on the card gets explained.

---

## Page 3 — Opportunity detail (`/opportunities/[id]`)

The core of the demo. Every number here is explained on the page itself — this is the page that answers "why should I trust this."

### Top strip
- **Horizon badge** (Now/Next/Later) + **domain badges**, plus a one-line reason (e.g. "Funded through 2027-05-31 (~9 mo)" or the converging-evidence explanation — see below).
- **Attractiveness / 100** — the headline number. See "The Attractiveness score" below for the full breakdown.
- **Evidence confidence %** — mean of the LLM classifier's own per-article confidence, under an anchored 4-tier rubric (not a raw unanchored self-report).
- **Supporting signals** — raw linked article count.
- **Momentum** — "+NN%" / "New" / "—". Explained below.

### "Why hot now" / "Why this matters" / "Recommended move"
Three fully deterministic, composed-from-clauses text fields — **no LLM call generates these**, they're template composition over already-structured data:
- **Why hot now**: one clause per recent (≤12 month) qualifying signal, strongest signal type first (buying signal > regulation > proof signal > competitor move > tech maturity > market trend), capped at 3, joined with " · ". One signal → one clause. No signal → an honest "No recent external signal on record."
- **Why this matters**: always exactly 2 clauses — a domain/vertical framing sentence, then a right-to-win sentence. **Say this plainly**: there's no CRM/accounts/deals data in this app yet, so the right-to-win clause currently always reads "no direct right-to-win evidence yet — early-stage watch." It's built and tested to activate the moment that data exists.
- **Recommended move**: a 9-cell matrix (role mode × horizon) plus an action clause keyed to the dominant signal type. This is *why* it changes when you switch role mode on Page 2/3 — same topic, different answer for a Strategist vs. a Salesperson.

### "Why this score" — the Attractiveness breakdown
This is the answer to "how is this number calculated." Five weighted components, shown with their individual value, their weight, and a progress bar:

| Component | Weight | What it measures | How |
|---|---|---|---|
| Market signal strength | 30% | Volume of evidence, weighted toward recent | Each article's weight halves every ~9 months; normalized against the strongest space on the radar |
| Source credibility | 20% | Trustworthiness of the publishers | 9-tier fixed anchor table (institutional feed → wire service → trade press → aggregator); TED/CORDIS/procurement feeds hardcoded to the top tier |
| Evidence quality | 20% | Is the classifier's own confidence trustworthy | Mean per-article LLM confidence under the anchored rubric mentioned above |
| Novelty & momentum | 15% | Is this accelerating right now, relative to everything else on the radar | Percentile rank of (recent 90-day count − prior 90-day count) against every other space computed this run — not a fixed curve, so it's not dominated by the many spaces with only 1–2 articles |
| Strategic relevance | 15% | Does it fit what Orange actually prioritizes | Match against the priority use cases/technologies set on the Company page (see Page 4) |

**Any component with insufficient data is excluded from the weighted sum and the rest are rescaled** — a data gap never silently drags the score toward zero. That's shown right on the page as "No data yet" rather than a 0.

### "Why this timing" — the horizon explanation
Directly under the score breakdown. Shows the counts the rule actually acted on (how many Now-prior signals, from how many distinct sources, how many Next-prior) and which rule fired. The key line to say out loud: **"Now" requires converging evidence — at least 2 concrete signals from at least 2 different sources, with one of them recent** — a single tender, or two records from the same feed, lands in "Next" instead. This is what fixed the old version of this page, where the timing badge used to just be a bucket of the Attractiveness score itself (so "Next" was structurally unreachable). It's now fully independent of the score.

### "Signal types behind it"
Every linked article gets classified into one of six types (buying signal, regulation, proof signal, competitor move, market trend, tech maturity) — shown here with the count per type and the exact distinguishing question the classifier answered to assign it (e.g. "Did a named vendor launch, acquire or announce something?"). This is what both "Why hot now" and the horizon rule are built from underneath.

### "Persona relevance"
The buyer personas (CIO, CISO, COO, CDO, etc. — 8 total) this topic is relevant to, with the weight tier (Primary/Secondary/Peripheral) and which table produced it (the use case, the business domain, or both agreeing). Feeds Sales mode's persona-weighted sort and the "Recommended move" persona slot.

### "Right to win & proof points" / "Offering & partner matches"
Both are honest placeholders right now — say so directly rather than skip past them. They keep their place in the layout in every role mode (never hidden, only collapsed) so adding real data later is a config change, not a redesign.

### "Momentum" tile, decoded
"+NN%" = actual period-over-period change in linked-evidence count (last 90 days vs. the 90 before). "New" = evidence exists but nothing prior to compare. "—" = not enough dated evidence at all. (The number that feeds the *score* is a peer-ranked version of this — see Novelty & momentum above — but the badge itself always shows the true percentage.)

---

## Page 4 — Company (`/company`)

Two distinct sections — worth being explicit that they are *not* the same thing if asked:
1. **Company profile** (name, geography, website, focus, reference documents) — describes the *customer/prospect* being pitched to.
2. **Orange priorities** — a separate chip-toggle picker where you select which use cases and technologies Orange itself is prioritizing. **This is the direct input to the Strategic relevance component (15%)** on every opportunity's score. Leave it empty and that component stays unscored, not zero — the callout on the page says this explicitly.

---

## Page 5 — Sources (`/sources`)

Shows the institutional backbone (TED, CORDIS, OCDS) plus a "priority watchlist" where the team can add specific market/partner/customer sources to track. Lighter page — mainly useful to show the evidence base is curated, not just scraped indiscriminately.

## Page 6 — Discovery (`/discovery`)

A focused, on-demand search tool (SearXNG/Tavily-backed) for going beyond the institutional backbone when a specific market, competitor or regulation deserves a closer look outside the automated pipeline.

## Page 7 — Reports (`/reports`)

Generates presentation-ready business case reports — either a full portfolio report or a focused report on one opportunity — pulling from the same underlying data as the detail page.

## Page 8 — Refresh (`/refresh`)

The controls to run the actual pipeline: collect evidence, build the corpus, classify with the LLM, recompute opportunity spaces. Shows live progress and the latest run's stats (articles processed, tokens spent, spaces produced). Good page to show if asked "how does new data get in."

## Page 9 — Settings (`/settings`)

AI provider/model config, search provider config. Not demo-critical, but confirms nothing here is hardcoded to one vendor.

## Page 10 — Help (`/help`)

A plain-language glossary of every term used across the app (Attractiveness, Confidence, Now/Next/Later, etc.) — worth pointing to at the end as "if anyone forgets what a term meant, it's all defined here."

---

## Quick-reference: every number and its one-line answer

| Number | One-line answer |
|---|---|
| Attractiveness (0–100) | Weighted sum of 5 components; missing components excluded and rescaled, never zeroed |
| Evidence confidence % | Mean LLM classification confidence, anchored rubric |
| Momentum (+NN%/New/—) | Real 90-day-vs-prior-90-day evidence count change |
| Horizon (Now/Next/Later) | Signal-type-driven convergence rule — independent of the Attractiveness score |
| Signal type counts | Each article answers one fixed distinguishing question, highest-priority type wins ties |
| Persona weight (Primary/Secondary/Peripheral) | Deterministic table: use case × persona, unioned with domain × persona, `max()` not sum |
| Business domain | Deterministic: technology's domain ∪ use case's domain; primary always from technology |
| Region/geography | Deterministic from structured sources (TED/CORDIS/OCDS); LLM-inferred from text for RSS |
| Strategic relevance | Match against Orange's own priorities set on the Company page |

## Things to say proactively if they don't come up

- **Nothing here is a black box** — every score has a visible "why" breakdown on the detail page; that was a hard requirement from the original brief, not an afterthought.
- **Missing data is never faked as zero** — every component that lacks data says so and steps out of the weighted average.
- **Known current gaps** (say these before someone finds them): no right-to-win/CRM data yet (affects "Why this matters" and the Presales fit-score sort, which currently falls back to Attractiveness with a visible note); geography isn't shown as a badge yet, only filterable; GNews is currently paused as a source; a handful of countries (Greece notably, plus Cyprus/Malta/Turkey and a few others) don't yet have a home in the region table — flagged, not silently misfiled.
