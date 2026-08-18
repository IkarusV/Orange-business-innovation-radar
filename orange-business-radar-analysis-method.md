# Orange Business Innovation Radar: Analysis Method

## The Problem This Solves

Collecting sources is not enough. The team needs a repeatable way to decide:

- Which signals matter more than others
- Whether a theme is genuinely rising or merely mentioned often
- How a set of sources becomes an attractiveness, urgency, and right-to-win assessment

The core rule is:

> Do not score raw words. Score dated evidence records that are tagged using a controlled vocabulary.

The word `AI` appearing 100 times does not prove an opportunity is important. A new regulation, a named buyer tender, and a deployed customer reference are stronger evidence because they describe a concrete event.

## Unit of Analysis: An Evidence Record

Every collected article, case study, announcement, regulation, or market-data event should become one or more evidence records.

Each record must contain:

| Field | Example |
| --- | --- |
| Source | Official regulator, Orange Business case study, analyst report |
| Publication date | `2026-08-15` |
| Claim | A government published a cloud-sovereignty procurement notice |
| Signal type | Buying signal |
| Vertical | Public sector |
| Use case | Sovereign AI data processing |
| Technology | Trusted cloud; AI |
| Geography | France |
| Source quality | 5/5 for official procurement source |
| Source URL | Canonical URL |
| Orange relevance | Existing offer, partner, customer reference, or none |

One source may yield multiple evidence records only if it makes multiple distinct claims. Do not create multiple records by splitting or repeating the same claim.

## Controlled Vocabulary: The Standard Point

The standard point is a maintained taxonomy, not a list of frequently used words.

### 1. Vertical Dictionary

Use a fixed list based on Orange Business target verticals, for example:

- Banking, finance, and insurance
- Public sector and government
- Healthcare and life sciences
- Manufacturing and smart industry
- Retail
- Energy
- Transportation and logistics
- Defense

### 2. Use-Case Dictionary

Use concrete business problems, not generic capabilities:

- Secure WAN visibility
- Claims deflection
- Cloud infrastructure modernization
- Safety-compliance monitoring
- Supply-chain traceability
- Customer-service automation
- IT operations automation

### 3. Technology Dictionary

Use technologies and delivery models:

- Trusted cloud
- Sovereign cloud
- AI / agentic AI
- Private 5G
- Edge computing
- SD-WAN / SASE
- Security analytics
- Computer vision

### 4. Synonym Map

Map alternate spellings and marketing names to one canonical term. For example:

| Raw phrase | Canonical tag |
| --- | --- |
| Zero Trust Network Access; ZTNA | Zero Trust |
| SASE; Secure Access Service Edge | SASE |
| GenAI; generative artificial intelligence; LLM | Generative AI |
| private LTE; private 4G; private 5G | Private wireless |

Maintain this dictionary as the team discovers new terminology. This is how comparisons stay consistent.

## Words: Useful for Discovery, Not Final Ranking

Word and phrase analysis can find candidate themes, but it must not decide the radar ranking.

### Discovery Analysis

Use document frequency, phrase extraction, and optionally TF-IDF to find terms that are:

- Repeated in recent documents
- Distinctive compared with a baseline corpus
- Co-occurring with a vertical and a use case

Example: `private 5G` alone is not a topic. `Private 5G + worker safety + chemicals` is a candidate opportunity space.

### Term Importance Diagnostic

If the team wants a numerical word/phrase importance measure, calculate it against a fixed baseline:

`Term diagnostic = 40% weighted document coverage + 30% distinctiveness versus baseline + 20% recency + 10% vertical/use-case specificity`

- **Weighted document coverage:** number of independent documents containing the term, weighted by source quality.
- **Distinctiveness versus baseline:** whether the term appears more often in the current relevant corpus than in the broader baseline corpus. TF-IDF or log-odds lift can be used.
- **Recency:** newer documents receive more weight; use a consistent time-decay rule.
- **Specificity:** terms connected to a named vertical and use case rank above generic terms.

Use this result only to prioritize research. Do not display it as the opportunity attractiveness score.

### Baseline Corpus

For fair comparison, define the baseline before analysis:

- Current corpus: sources collected during the selected period for a vertical/domain, for example the last 90 days.
- Baseline corpus: the same source categories over the preceding 12 months, or a cross-industry source collection over the same period.
- Keep language, source categories, and date range consistent where possible.

Without a baseline, a frequent word only means it was mentioned often. It does not show whether it is rising.

## Evidence Weighting Rules

Assign every evidence record a score using four inputs:

`Evidence Weight = Source Quality x Signal-Type Weight x Recency Weight x Specificity Weight`

Source quality must come from the layered source model and the source registry/backlog, not from an AI model's unconstrained judgment. See `source_registry.csv` for verified RSS sources and `source_backlog.csv` for authoritative sources that need separate collection methods.

### Source Quality: 1-5

| Score | Source type |
| --- | --- |
| 5 | Official regulation, procurement notice, named customer announcement, audited filing |
| 4 | Reputable analyst research, named case study with a measurable outcome, major industry publication |
| 3 | Official vendor or partner announcement without independent confirmation |
| 2 | General media coverage, opinion article, unverified vendor claim |
| 1 | Unsourced claim, repost, generic marketing content |

### Signal-Type Weight: 1-5

| Signal type | Weight | Reason |
| --- | --- | --- |
| Regulation | 5 | Creates a formal compliance or budget trigger |
| Buying signal | 5 | Shows active customer demand or procurement |
| Proof signal | 4 | Shows a real deployment, contract, pilot, or outcome |
| Market move | 3 | Shows investment, acquisition, partnership, or competitor action |
| Technology maturity | 3 | Shows production readiness or a capability threshold |
| Market trend | 2 | Indicates direction but may not prove buyer action |

### Recency Weight

Use a simple, transparent rule:

| Evidence age | Weight |
| --- | --- |
| 0-90 days | 1.0 |
| 91-180 days | 0.8 |
| 181-365 days | 0.6 |
| More than 365 days | 0.4 |

### Specificity Weight

| Evidence content | Weight |
| --- | --- |
| Names vertical, use case, technology, and buyer or deployment | 1.0 |
| Names vertical, use case, and technology | 0.8 |
| Names technology and one other dimension | 0.6 |
| Generic technology mention | 0.3 |

## From Evidence Records to Opportunity Scores

Group records by the canonical opportunity space:

`Vertical x Use Case x Technology`

Do not allow duplicate articles, syndicated press releases, or multiple reports of the same event to inflate the score. Count the event once and retain all supporting URLs under it.

### Attractiveness: 0-100

| Component | Calculation rule |
| --- | --- |
| Market signal strength, 30 points | Sum capped evidence weights from independent external events. More high-quality demand, regulation, and proof signals earn more points. |
| Source diversity, 20 points | Count distinct source categories, not URLs: regulation, buyer/procurement, analyst, industry media, technology maturity, market move. |
| Evidence quality, 20 points | Average source quality, with a minimum of two independent sources required for a score above 60. |
| Novelty/momentum, 15 points | Compare weighted evidence volume in the current period with the baseline period. Rising evidence earns points; no historical data is marked `not yet measurable`, not assumed rising. |
| Strategic relevance, 15 points | Apply a pre-agreed Orange Business relevance matrix using domains and priority verticals. |

### Urgency: 0-100 and Horizon

| Component | Evidence |
| --- | --- |
| Deadline pressure, 40 points | Regulation, contractual deadline, tender closing date, or known compliance date |
| Buyer activity, 35 points | Procurement, budget, RFP, task force, or named customer initiative |
| Market timing, 25 points | Technology production maturity, competitor launch, investment, or accelerating adoption |

Map the result to a horizon:

- `Now`: 70-100
- `Next`: 40-69
- `Later / Watchlist`: 0-39

### Right to Win: 0-100

| Component | Calculation rule |
| --- | --- |
| Offering / asset fit, 30 points | Relevant current Orange offer or operational asset |
| Customer overlap, 25 points | Named customers or target accounts in the vertical/geography |
| Reference cases, 25 points | Verified deployments, pilots, contracts, or quantified outcomes |
| Skills and partner readiness, 20 points | Relevant implementation capability, accredited partner status, managed-service capability, and joint delivery evidence |

## Financial-Market Signals

Yahoo Finance data is only a supplementary `market move` record.

Create a financial-market evidence record only when all conditions hold:

1. A named event exists, such as a contract, investment, acquisition, product launch, or regulation.
2. The event relates directly to the candidate opportunity space.
3. The market reaction occurs near the event date.
4. The reaction is compared with a broader market or relevant industry index.
5. At least one independent source confirms the event's relevance.

Share-price movement without an identified event is not included in scoring.

## Minimum Evidence Thresholds

| Radar state | Requirement |
| --- | --- |
| Watchlist candidate | At least one credible evidence record; score remains provisional |
| Publishable topic | At least three independent evidence records, including one demand, regulation, or proof signal |
| High-confidence topic | At least five independent records across at least three signal types, plus Orange right-to-win evidence |

## Human Review

Scores prioritize attention; they do not replace judgment. Before publishing, a reviewer checks:

- The opportunity is specific and not a generic technology label
- Evidence records support the stated conclusion
- Duplicate reporting has not inflated the score
- The recommended action follows logically from the evidence and right-to-win proof
- Uncertainty and evidence gaps are visible
