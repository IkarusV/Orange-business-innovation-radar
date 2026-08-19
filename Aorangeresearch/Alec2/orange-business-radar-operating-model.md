# Orange Business Innovation Radar: Operating Model

For the detailed method that converts sources into comparable scores, see `orange-business-radar-analysis-method.md`.

## Goal

Build a living innovation radar that identifies **specific, explainable, and actionable** opportunities for Orange Business.

The radar is not a list of technologies. Each radar entry is an opportunity space:

`Opportunity Space = Vertical x Use Case x Technology`

Example: `Banking x secure WAN visibility x network security analytics`.

## The Two Questions Every Topic Must Answer

| Question | Decision | Evidence needed |
| --- | --- | --- |
| Is this opportunity worth pursuing? | Market attractiveness and urgency | Independent market, customer, regulatory, and technology evidence |
| Can Orange Business credibly deliver and win? | Right to win | Orange offerings, customer references, partner readiness, and delivery capability |

These questions must be scored separately. A familiar Orange technology is not automatically an attractive market opportunity, and a high-growth market is not automatically one that Orange Business can win.

## How To Define an Opportunity Space

| Dimension | Definition | Test |
| --- | --- | --- |
| Vertical | A target industry with a material business trigger or demand | Is there a relevant buyer, budget, risk, regulation, or operational pressure? |
| Use case | A specific customer problem with measurable value | Does it solve a concrete operational, security, customer, or compliance problem? |
| Technology | The enabling technology or delivery approach | Is it mature enough or gaining credible market momentum? |

Orange Business expertise, existing customers, and partners do not define market demand. They are evidence of the right to win once the opportunity is identified.

## Evidence Architecture

### External Evidence: Why the Opportunity Is Attractive

Use independent sources to establish market demand and urgency:

- Regulations, standards, and compliance deadlines
- Customer announcements, tenders, and procurement activity
- Analyst research and credible market data
- Industry news and competitor investments
- Technology production-readiness evidence

### Orange Business Evidence: Why We Can Win

Use Orange-owned sources to establish credibility and actionability:

- Existing offers and managed services
- Customer case studies, deployments, pilots, and measurable outcomes
- Partner relationships and delivery accreditations
- Customer-account and vertical overlap
- Delivery skills, infrastructure, and operational capability

### Layered Source Model

Use sources according to the claim being made. Do not treat all sources as equally authoritative.

| Layer | Purpose | Examples | Typical quality |
| --- | --- | --- | --- |
| Primary policy and enforcement | Binding requirements, formal deadlines, public policy | EUR-Lex, European Commission, ENISA, ANSSI, EU AI Office, EDPB | 5/5 |
| Primary technical | Standards, architecture, technical maturity, control requirements | ETSI, 3GPP, NIST, CISA, MITRE ATT&CK, ISO/IEC | 4-5/5 |
| Analyst and research | Market direction, adoption, spending, category definitions | Gartner, IDC, Forrester, Omdia, ABI Research, STL Partners, Stanford AI Index | 3-4/5 |
| Industry adoption | Sector deployment, ecosystem, and adoption context | GSMA, WEF, IEA, OPC Foundation, Plattform Industrie 4.0 | 3-5/5 |
| Independent media | Early discovery, market moves, named announcements | RSS media sources, NPR Business, Business Insider, EU-Startups | 2-4/5 |
| Orange Business evidence | Offers, references, partners, assets, and strategy | Orange Business, Orange Cyberdefense, Orange Press, Orange Innovation | 3/5 for market claims; strong for Right to Win |

`source_registry.csv` contains only verified RSS feeds. `source_backlog.csv` tracks authoritative sources that require other collection methods, such as publication portals, newsletters, subscriptions, manual search, or selected official RSS feeds.

### Source-Use Rules

- Use regulation and standards sources to validate deadlines, mandatory requirements, terminology, and technical maturity.
- Use analyst and industry sources to support market direction, adoption, and business-model claims.
- Use independent media to discover candidate events and corroborate named market moves.
- Use Orange-owned material to establish Orange Business's offers, partnerships, assets, and references, not as the sole proof of external demand.
- Treat all vendor and startup announcements as claims until corroborated by a customer, regulator, independent source, or measurable proof point.
- Verify every source URL and claim before it affects a published score. The source list collected through research tools is a candidate backlog, not validated evidence by itself.

### Partner Evidence

Partner tiers, such as Advanced, Diamond, ELITE, Platinum, and Titanium, are vendor-specific. They are evidence of partner readiness, not a universal ranking and not proof of market demand.

For each partner activity, capture the named partner, Orange Business role, customer/reference, use case, technology, outcome, date, and source URL in `orange-business-partner-activities.csv`.

## Scorecard

### 1. Opportunity Attractiveness: Is the Market Worth Pursuing?

`Attractiveness = 30% market signal strength + 20% source diversity + 20% evidence quality + 15% novelty/momentum + 15% Orange Business strategic relevance`

| Factor | Meaning |
| --- | --- |
| Market signal strength | Magnitude of demand, growth, investment, buyer activity, or problem severity |
| Source diversity | Evidence repeated across independent source types |
| Evidence quality | Credibility, specificity, recency, and quantitative support |
| Novelty and momentum | Whether the opportunity is rising, changing, or reaching production maturity |
| Strategic relevance | Alignment with Orange Business domains and strategic priorities |

### 2. Right to Win: Can Orange Business Deliver?

`Right to Win = 30% offering/asset fit + 25% customer overlap + 25% reference cases + 20% skills and partner readiness`

| Factor | Meaning |
| --- | --- |
| Offering / asset fit | Relevant Orange offer, infrastructure, managed service, or capability |
| Customer overlap | Existing customers and addressable accounts in the relevant vertical/geography |
| Reference cases | Proven deployments, pilots, contracts, or measurable outcomes |
| Skills and partner readiness | Delivery teams, partner tier, certifications, integration capability, and joint go-to-market readiness |

### 3. Urgency: When Is the Window?

| Horizon | Meaning |
| --- | --- |
| Now | Active buyer signal, live tender, imminent deadline, or production-ready technology with immediate demand |
| Next | Clear momentum and an expected 12-24 month demand window |
| Later / Watchlist | Credible early signal but limited buyer trigger, weak evidence, or immature technology |

### 4. Confidence: How Trustworthy Is the Ranking?

| Confidence | Minimum condition |
| --- | --- |
| High | Multiple recent, independent, credible sources plus relevant Orange Business evidence |
| Medium | Enough evidence to validate and test the topic, with known gaps |
| Low | Early signal, vendor-led claim, or single-source evidence only |

## Signal Taxonomy

Tag every evidence item with one type:

- Regulation
- Buying signal
- Market trend
- Market move
- Technology maturity
- Proof signal

## Financial-Market Data Rule

Yahoo Finance or other market data can be used only as a supplementary **market move** signal.

It is valid only when a named, relevant event explains the market reaction, such as a contract, investment, acquisition, regulation, product launch, or earnings guidance. Validate the event with independent sources and compare the movement with the broader market or relevant industry index.

Do not use share-price movement alone as evidence of attractiveness or urgency. It is often affected by macroeconomic factors or company-specific factors unrelated to the opportunity space.

## Research Workflow

1. Collect external signals from regulations, tenders, market research, industry news, technology maturity evidence, and relevant market moves.
2. Extract candidate themes and convert them into `Vertical x Use Case x Technology` opportunity spaces.
3. Reject generic entries such as `AI`, `cloud`, or `cybersecurity` without a vertical and use case.
4. Gather Orange Business and partner evidence for each candidate using official case studies, blogs, partner pages, and announcements.
5. Store partner activity evidence in `orange-business-partner-activities.csv`, with one row per source-backed activity.
6. Score attractiveness, right to win, urgency, and confidence separately.
7. Publish only topics whose score explanation includes dated sources and a clear next action.
8. Keep incomplete but credible topics in the watchlist, with a planned refresh date.

## Topic Card: Minimum Published Output

Every published radar topic must show:

- Opportunity space
- Attractiveness score and factor breakdown
- Right-to-win score and factor breakdown
- Urgency / time horizon
- Confidence level and last refresh date
- Dated source evidence and signal types
- Why hot now
- Why this matters to the customer and Orange Business
- Orange Business proof points
- Recommended next action

## Decision Rules

| Situation | Radar treatment |
| --- | --- |
| High attractiveness + high right to win | Prioritize for innovation investment and a commercial play |
| High attractiveness + low right to win | Watchlist or assess offering, capability, and partner gaps |
| Moderate attractiveness + high right to win | Use for account expansion and reference-led sales activities |
| Low confidence | Do not publish as ranked; keep as a watchlist candidate |

## Current Work

- The strategic focus is strongest around cybersecurity, trusted cloud, trusted AI, secure connectivity, and selected regulated/industrial verticals.
- The initial partner map contains 20 technology and delivery partners.
- The next dataset to build is the source-backed record of what Orange Business has actually delivered with each partner.
- After partner activities and customer references are captured, group repeated patterns into candidate opportunity spaces and validate them with independent external signals.

## Implementation Roadmap: From RSS to a Scored Radar

Use a hybrid approach:

- **Python** for collection, normalization, deterministic rules, deduplication, joins, and scoring.
- **AI agents / LLMs** for semantic tasks: extracting claims, assigning tags, detecting new synonym candidates, and proposing Orange Business relevance links.
- **Human reviewers** for high-impact evidence, taxonomy changes, and publication decisions.

AI agents must not directly publish a score. Every score must remain traceable to reviewed, source-backed evidence records.

### Priority Tasks

| Priority | Task | Missing parts solved | Main implementation |
| --- | --- | --- | --- |
| 1 | Build a source registry | Source quality, source category, independence | Configuration file and team setup |
| 2 | Build the controlled taxonomy | Vertical, use case, technology, canonical synonyms | Team approval with AI suggestions |
| 3 | Preserve and enrich raw article collection | Full text, canonical URLs, provenance | Python |
| 4 | Extract evidence records | Claims, tags, signal types | AI extraction with validation rules |
| 5 | Deduplicate real-world events | Event-level duplicate handling | Python with AI/human review for uncertain matches |
| 6 | Calculate deterministic evidence measures | Specificity, source quality, recency | Python |
| 7 | Link Orange Business data | Orange relevance and right to win | Python joins plus AI-assisted matching |
| 8 | Aggregate opportunity spaces | Attractiveness, urgency, confidence | Python |
| 9 | Review and publish | Trustworthy radar entries | Human review |

### 1. Source Registry

Create `source_registry.csv` before expanding collection. It establishes the baseline for source quality, category, and independence.

```csv
source,feed_url,source_category,source_quality_default,independence_group,domain,active
EUR-Lex,https://...,regulator,5,eu_institutions,regulation,true
Manufacturing Dive,https://...,industry_media,4,industry_dive,smart_industries,true
AWS Blog,https://...,vendor,3,aws,cloud,true
```

Required fields:

- `source_category`: regulator, procurement, customer, analyst, industry_media, vendor, partner, Orange-owned
- `source_quality_default`: 1-5 default quality assessment
- `independence_group`: publisher or institution group used to avoid treating related sources as independent
- `active`: controls which feeds are automatically ingested

Vendor feeds are useful discovery sources, but they should not independently make an opportunity highly attractive.

### 2. Controlled Taxonomy and Synonym Map

Create controlled lists for verticals, use cases, and technologies. Use examples such as:

```text
verticals:
- Banking, finance, and insurance
- Public sector and government
- Manufacturing and smart industry
- Healthcare and life sciences

use_cases:
- Secure WAN visibility
- Safety-compliance monitoring
- Claims deflection
- Supply-chain traceability

technologies:
- Trusted cloud
- Generative AI
- Private wireless
- Edge computing
- SASE
```

Create `synonym_map.csv` to map variations to a canonical tag:

```csv
raw_term,canonical_tag,tag_type
ZTNA,Zero Trust,technology
Secure Access Service Edge,SASE,technology
GenAI,Generative AI,technology
LLM,Generative AI,technology
Private LTE,Private wireless,technology
Private 5G,Private wireless,technology
```

AI can propose new terms, but the team must approve taxonomy additions. This prevents inconsistent labels from corrupting comparisons.

### 3. Data Pipeline

Keep raw RSS data immutable. Use this pipeline:

```text
RSS feeds
  -> rss_digest.csv
  -> article_content.csv
  -> evidence_records.csv
  -> events.csv
  -> opportunity_scores.csv
```

- `rss_digest.csv`: raw RSS metadata and summaries.
- `article_content.csv`: canonical URL, full readable article text, fetch date, and publication date.
- `evidence_records.csv`: one source-supported claim per row, tagged to the controlled taxonomy.
- `events.csv`: deduplicated real-world events with links to all supporting evidence records.
- `opportunity_scores.csv`: aggregated results for each `Vertical x Use Case x Technology` opportunity space.

RSS summaries can be insufficient for claim extraction, so the collection pipeline should fetch and store readable canonical article content where permitted.

### 4. AI-Assisted Claim Extraction

For each article, an extraction agent should return structured records. It must use only the controlled taxonomy and provide a direct supporting quote.

```json
{
  "claims": [
    {
      "claim": "A manufacturer issued a private-5G procurement notice for safety monitoring.",
      "signal_type": "buying_signal",
      "vertical": "Manufacturing and smart industry",
      "use_case": "Safety-compliance monitoring",
      "technology": ["Private wireless", "Edge computing"],
      "geography": "France",
      "named_organizations": ["Example Manufacturer"],
      "evidence_quote": "..."
    }
  ]
}
```

Agent rules:

- Extract only claims supported by the source text.
- Include an evidence quote for every claim.
- Use `unknown` rather than guessing missing fields.
- Do not invent customer names, dates, market statistics, outcomes, or regulations.
- Mark unclear cases for human review.

### 5. Deterministic Specificity Calculation

Python should calculate specificity from completed evidence fields:

| Evidence contains | Specificity score |
| --- | --- |
| Vertical, use case, technology, and named buyer/deployment | 1.0 |
| Vertical, use case, and technology | 0.8 |
| Technology and one other dimension | 0.6 |
| Generic technology mention only | 0.3 |

This should not be an unconstrained AI judgment.

### 6. Event-Level Deduplication

Multiple articles may describe the same tender, deployment, regulation, partnership, or investment. Prevent this from artificially inflating scores.

Apply these checks in order:

1. Same canonical URL or GUID: automatic duplicate.
2. Same normalized title: likely duplicate.
3. Same named organization, date, and similar claim: likely same event.
4. Semantic claim similarity: create a candidate duplicate cluster.
5. Use AI or human review only for uncertain clusters.

Create one `event_id` for each real-world event and attach all evidence-record IDs to it.

### 7. Orange Relevance and Right-to-Win Links

For each opportunity space, link the evidence to:

- Orange Business offers and operational assets
- The 20-partner activity dataset in `orange-business-partner-activities.csv`
- Customer references, deployments, and proof points
- Relevant customer-account and vertical overlap
- Skills, certifications, and partner delivery readiness

The link is based on the shared canonical dimensions:

`Vertical + Use Case + Technology`

This transforms an external opportunity into a right-to-win assessment.

### AI Agent Roles

| Agent | Responsibility |
| --- | --- |
| Collection agent | Checks feeds, fetches canonical articles, and records provenance |
| Extraction agent | Extracts source-supported claims and canonical tags |
| Taxonomy agent | Proposes new terms and synonyms for human approval |
| Deduplication agent | Reviews uncertain event clusters |
| Orange-fit agent | Matches opportunities to offers, partners, and references |
| Quality-review agent | Detects unsupported claims, missing URLs, weak evidence, and duplicate inflation |

### Human Review Rules

Require human review when:

- The record is the only evidence supporting a topic.
- Attractiveness or urgency is above 70.
- A regulation, customer contract, market-size figure, or financial-market event affects a score.
- AI confidence is low or tags are `unknown`.
- A new canonical taxonomy term is proposed.

The first implementation milestone is not the final dashboard. It is a source registry, approved taxonomy, and reviewed `evidence_records.csv` dataset. These create the standard needed for comparable scoring.
