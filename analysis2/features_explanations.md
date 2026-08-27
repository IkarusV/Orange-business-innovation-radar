# Feature Measurement Explanations

## Purpose

This document explains exactly how the current Innovation Radar calculates:

```text
Attractiveness
Orange fit
Confidence
Urgency
Priority
Radar / Watchlist status
Market potential
```

For every feature, it documents:

1. the business concept we intended to represent;
2. the evidence fields actually used by the code;
3. the implemented formula;
4. why the MVP used that formula;
5. a worked example;
6. what the result can legitimately mean; and
7. what the result cannot prove.

This is an audit of the current implementation, not a defense of it. Several
feature names are stronger than their present measurements.

---

# 1. Executive truth table

| Displayed feature | What the current code really measures | Validation state | Safer current name |
|---|---|---|---|
| `attractiveness_score` | Weighted external evidence signal, source-name breadth, source prior and event-key breadth | Deterministic but weights not empirically validated | `external_evidence_score` |
| `orange_fit_score` | Number of distinct keyword groups matched across the evidence | Provisional and not Orange-approved | `provisional_capability_match_score` |
| `confidence_score` | Evidence-row volume, average source prior and distinct source-name count | Evidence-support proxy | `evidence_support_score` |
| `urgency_score` | Percentage of records classified as regulation, buying signal or market move | Trigger-density proxy; no deadline calculation | `urgent_signal_share` |
| `priority_score` | Weighted combination of the four indices above | Subjective MVP weighting; contains overlapping components | `mvp_priority_index` |
| Market size | Enterprise-count and adoption scenarios multiplied by approved annual values | Method implemented; no approved EUR outputs yet | `annual_addressable_potential_scenario` |

## The central limitation

The code produces **indices**, not statistically validated predictions.

```text
Index = several selected variables combined according to business rules
Prediction = estimated future outcome validated against observed outcomes
```

The current system has no historical Orange opportunity outcomes, sales
pipeline, wins, losses, revenue or profitability data. Therefore it cannot
currently prove that a score predicts commercial success.

The correct stakeholder statement is:

> These scores consistently prioritize external evidence under explicit MVP
> rules. They are not yet calibrated predictions of market success or Orange's
> probability of winning.

---

# 2. Unit of measurement

The system does not score an individual article as the final business object.
It groups eligible articles into one:

```text
Opportunity = Vertical × Use Case × Technology
```

The grouping code uses:

```python
GROUP_COLUMNS = ["vertical", "use_case_id", "technology_id"]
```

Example:

```text
Public/Gov sector × compliance monitoring × cybersecurity platform
```

All feature calculations below happen within the group of evidence records
assigned to the same opportunity.

## Eligibility before measurement

An evidence row enters scoring only when:

```text
vertical, use_case_id and technology_id are present
classification_status = classified
enrichment_status = ready_for_scoring
date_quality_flag = valid_past
```

Duplicate `article_id` values are removed first. In the current run:

```text
576 input rows
338 eligible evidence rows
238 excluded rows
205 opportunity groups
```

Evidence:

```text
Analysis/outputs/enrichment/auto_scoring_candidates.csv
Analysis/outputs/scoring/opportunity_evidence.csv
Analysis/outputs/scoring/scoring_exclusions.csv
Analysis/outputs/scoring/scoring_summary.csv
```

---

# 3. Evidence variables created before scoring

## 3.1 Signal type

`04b_auto_enrich_candidates.py` searches title, summary, classification evidence,
use case and technology fields for explicit signal terms.

The current signal rule order is:

```text
regulation
buying_signal
market_move
proof_signal
technology_maturity
market_trend
unknown
```

The first rule with a matching term becomes the record's signal type.

Examples:

| Signal | Example terms |
|---|---|
| Regulation | regulation, directive, legislation, compliance requirement |
| Buying signal | tender, procurement, RFP, contract award, budget |
| Market move | partnership, acquisition, rollout, deployment, investment |
| Proof signal | case study, pilot, demonstrator, implemented |
| Technology maturity | certified, interoperable, production-ready |
| Market trend | growing demand, shortage, increasing demand |

Signal type is rule-based. It is not generated from a trained statistical model.

## 3.2 Signal points

`05_score_opportunities.py` converts the category to ordinal points:

| Signal type | Points |
|---|---:|
| Regulation | 4 |
| Buying signal | 4 |
| Market move | 3 |
| Proof signal | 3 |
| Technology maturity | 2 |
| Market trend | 2 |
| Unknown | 1 |

### Why this scale was chosen

The MVP assumes that regulation and demonstrated purchasing behavior provide
stronger action evidence than a broad trend. A deployment or proof is placed in
the middle, while unknown evidence receives the minimum rather than zero.

### Statistical status

This is an **ordinal business scale**. The difference between 4 and 3 has not
been proven to be economically equal to the difference between 3 and 2. The
points are not probabilities.

## 3.3 Source-quality prior

`04_enrich_candidates.py` assigns quality by source type:

| Source type | Prior |
|---|---:|
| TED | 0.90 |
| OCDS UK / Ukraine | 0.90 |
| CORDIS | 0.80 |
| RSS | 0.55 |
| GNews | 0.45 |
| Unknown | 0.30 |

### Why this measurement was chosen

Institutional procurement and EU research records are treated as stronger
primary evidence than a generic discovery feed. A fixed prior creates a
consistent rule when no article-level fact-checking score exists.

### Limitation

The prior measures source-type preference, not whether one specific claim is
true. A TED notice can still be irrelevant, and a high-quality news article can
still receive the lower GNews prior.

## 3.4 Source independence

The scoring code calculates:

```python
independent_sources = number of distinct source_name values
```

### Why this measurement was chosen

Several source names provide more triangulation than one source name. The count
is simple, auditable and available in the existing data.

### Limitation

This is not fully measured independence. Two publishers may have the same owner,
or several sources may repeat one press release. The field
`source_independence_group` exists upstream, but the current scoring code does
not use it; it uses `source_name`.

## 3.5 Event independence

An event key is built as:

```text
canonical URL, when available
otherwise article_id
```

The scoring code counts distinct `event_key` values.

### Why this measurement was chosen

The intention was to stop the same item from being counted repeatedly.

### Limitation

Different URLs describing the same real-world event are still counted as
different events. Therefore this is URL-level event separation, not robust event
deduplication.

## 3.6 Orange capability groups

The automatic rules detect these groups:

```text
connectivity
cloud_edge
cybersecurity
data_ai
industrial_operations
business_trigger
```

The output records the exact groups and terms in:

```text
auto_positive_groups
auto_matched_terms
```

### Critical limitation

`business_trigger` and `industrial_operations` are not necessarily Orange
Business capabilities. They are context or demand indicators. Because the
current Orange-fit formula counts all six groups equally, the implemented score
can overstate Orange fit.

---

# 4. Attractiveness feature

## 4.1 Intended business meaning

The intended question is:

> Does the external market show strong enough activity to justify investigating
> this opportunity?

## 4.2 Evidence actually measured

The code measures four things:

| Component | Observed variable | Maximum points |
|---|---|---:|
| Signal | Mean signal points | 30 |
| Independence | Distinct source names | 25 |
| Quality | Mean source-quality prior | 25 |
| “Momentum” | Distinct event keys | 20 |

## 4.3 Exact formula

Let:

```text
s̄ = mean signal points
S = number of distinct source names
q̄ = mean source-quality prior
E = number of distinct event keys
```

Then:

```text
Signal component       = min(s̄ / 4, 1) × 30
Independence component = min(S / 3, 1) × 25
Quality component      = min(q̄, 1) × 25
Momentum component     = min(E / 5, 1) × 20

Attractiveness = Signal + Independence + Quality + Momentum
```

Maximum = 100.

## 4.4 Why these variables and weights were chosen

The MVP reasoning was:

1. Signal type receives the largest weight because evidence of regulation,
   purchasing or deployment is closer to market action than generic coverage.
2. Source breadth and source quality each receive 25 points because evidence
   should be both corroborated and credible.
3. Event breadth receives 20 points to reward repeated activity without allowing
   unlimited article volume to dominate.
4. The caps create saturation: three source names and five event keys are enough
   for the maximum respective component.

## 4.5 Statistical status of the weights

The weights `30/25/25/20` were selected as explainable MVP business assumptions.
They were not estimated using regression, historical Orange outcomes, customer
research, conjoint analysis, or expert calibration.

Therefore, the formula is reproducible but not statistically validated as a
measure of true market attractiveness.

## 4.6 Worked example

Opportunity:

```text
Public/Gov sector × compliance monitoring × cybersecurity platform
```

Evidence observed:

| Source | Records | Signal | Prior |
|---|---:|---|---:|
| TED | 2 | Unknown | 0.90 |
| Gov Tech Review | 1 | Unknown | 0.55 |
| KPMG.com through GNews | 1 | Regulation | 0.45 |
| StateScoop through GNews | 1 | Regulation | 0.45 |
| CORDIS | 2 | Unknown | 0.80 |

Totals:

```text
evidence records = 7
distinct source names = 5
distinct event keys = 7
average quality = (0.90 + 0.55 + 0.45 + 0.90 + 0.45 + 0.80 + 0.80) / 7
                = 0.693
```

Five unknown signals receive 1 point and two regulation signals receive 4:

```text
mean signal points = (5 × 1 + 2 × 4) / 7
                   = 1.857
```

Components:

```text
Signal       = 1.857 / 4 × 30       = 13.9
Independence = min(5 / 3, 1) × 25   = 25.0
Quality      = 0.693 × 25           = 17.3
Momentum     = min(7 / 5, 1) × 20   = 20.0

Attractiveness = 13.9 + 25.0 + 17.3 + 20.0
               = 76.2
```

## 4.7 Correct interpretation of 76.2

The evidence set is broad across source names and URLs, and it has moderate
source quality. However, only two of seven records have a detected strong signal.

Correct statement:

> This opportunity has a comparatively strong and broad external evidence
> footprint under the MVP rules.

Incorrect statement:

> The market is 76.2% attractive or has a 76.2% chance of success.

## 4.8 Naming problem

The code calls distinct event count `momentum_component`. It does not use time
period growth. It should currently be called `event_breadth_component`.

A genuine momentum feature would compare periods, for example:

```text
recent_events = independent events in the latest 180 days
previous_events = independent events in the preceding 180 days

growth = (recent_events − previous_events) / max(previous_events, 1)
```

That calculation is not implemented in the current scoring file.

---

# 5. Orange-fit feature

## 5.1 Intended business meaning

The intended question is:

> Does this opportunity require capabilities that Orange Business could
> plausibly provide or integrate?

## 5.2 Evidence actually measured

The code unions all semicolon-separated values from `auto_positive_groups` for
the opportunity and counts distinct groups.

## 5.3 Exact formula

Let `G` be the number of distinct matched groups:

```text
Orange fit = min(G / 4, 1) × 100
```

Examples:

| Matched groups | Score |
|---:|---:|
| 0 | 0 |
| 1 | 25 |
| 2 | 50 |
| 3 | 75 |
| 4 or more | 100 |

## 5.4 Why this method was chosen

The MVP lacked internal Orange capability, offering, customer-reference and
competitor data. Counting explicit group matches provided a cheap, deterministic
first approximation of capability breadth.

The cap at four prevents opportunities with many repeated keywords from scoring
above 100.

## 5.5 Worked example

The Public/Gov compliance opportunity matched:

```text
business_trigger
cloud_edge
connectivity
cybersecurity
```

Therefore:

```text
G = 4
Orange fit = min(4 / 4, 1) × 100 = 100
```

Examples of stored matched terms include:

```text
cyber
security
compliance
cloud
network
connected
resilience
```

## 5.6 Correct interpretation of 100

Correct statement:

> The evidence matched four configured Orange-relevant keyword groups.

Incorrect statement:

> Orange has perfect fit or a 100% chance of winning.

## 5.7 Major validity problem

This feature is the weakest of the current decision scores because:

1. keyword presence does not prove a real service requirement;
2. `business_trigger` is counted as though it were a capability;
3. `industrial_operations` is industry context, not necessarily an Orange
   capability;
4. every group has equal weight;
5. no official Orange capability taxonomy is used in this formula;
6. no customer references, certifications or delivery proof are included; and
7. no competitor comparison is included.

The current value should not be presented as right-to-win.

## 5.8 Recommended future measurement

Separate the model into:

```text
Capability fit
Proof of delivery
Strategic priority
Competitive differentiation
Geographic coverage
```

One possible future framework is:

```text
Validated Orange fit =
30% approved capability match
+ 25% customer references and credentials
+ 20% geographic delivery coverage
+ 15% partner ecosystem
+ 10% strategic priority
```

These example weights must be approved by Orange stakeholders before use.

Right-to-win would additionally require competitor evidence and should remain a
separate feature.

---

# 6. Confidence feature

## 6.1 Intended business meaning

The intended question is:

> How strongly does the available evidence support this opportunity hypothesis?

## 6.2 Evidence actually measured

| Component | Variable | Maximum points |
|---|---|---:|
| Evidence sufficiency | Number of eligible evidence rows | 35 |
| Evidence quality | Mean source-quality prior | 35 |
| Source breadth | Number of distinct source names | 30 |

## 6.3 Exact formula

Let:

```text
N = number of evidence records
q̄ = average source-quality prior
S = number of distinct source names
```

Then:

```text
Evidence component     = min(N / 5, 1) × 35
Quality component      = min(q̄, 1) × 35
Independence component = min(S / 3, 1) × 30

Confidence = Evidence + Quality + Independence
```

## 6.4 Why this method was chosen

The MVP assumes that a conclusion is better supported when:

- it has several eligible evidence records;
- the average source prior is stronger; and
- the evidence comes from several source names.

The caps prevent large article volume from increasing confidence without limit.

## 6.5 Worked example

For the Public/Gov compliance opportunity:

```text
N = 7
q̄ = 0.693
S = 5

Evidence     = min(7 / 5, 1) × 35 = 35.0
Quality      = 0.693 × 35          = 24.3
Independence = min(5 / 3, 1) × 30 = 30.0

Confidence ≈ 35.0 + 24.3 + 30.0 = 89.2
```

## 6.6 Correct interpretation of 89.2

Correct statement:

> The hypothesis has a comparatively broad, multi-source evidence set under the
> current source priors.

Incorrect statement:

> We are 89.2% certain the opportunity is commercially valid.

## 6.7 Limitations

- Evidence count is not the same as factual corroboration.
- Distinct source names are not guaranteed independent owners.
- The quality prior applies to source type, not individual article accuracy.
- Human expert agreement is not included.
- No confidence interval is calculated.
- Source quality and source breadth also appear inside attractiveness.

The final point creates **double-counting** when attractiveness and confidence
are both used in priority.

---

# 7. Urgency feature

## 7.1 Intended business meaning

The intended question is:

> Does the opportunity contain a near-term reason for Orange Business to act?

## 7.2 Evidence actually measured

The code marks a record urgent when its `signal_type` is one of:

```text
regulation
buying_signal
market_move
```

## 7.3 Exact formula

Let:

```text
U = number of urgent-signal evidence records
N = total eligible evidence records
```

Then:

```text
Urgency = U / N × 100
```

## 7.4 Why this method was chosen

Regulation, procurement and active company moves can require a response sooner
than a generic market trend. Their share provides a simple, comparable trigger
indicator.

## 7.5 Worked example

The Public/Gov compliance opportunity contains:

```text
2 regulation records
0 buying-signal records
0 market-move records
7 total records
```

Therefore:

```text
Urgency = 2 / 7 × 100 = 28.6
```

## 7.6 Correct interpretation of 28.6

Correct statement:

> 28.6% of this opportunity's eligible evidence contains a detected urgent
> signal type.

Incorrect statement:

> Orange has 28.6 days to act or there is a 28.6% urgency probability.

## 7.7 Major validity problem

The current method does not use:

- regulatory effective dates;
- tender deadlines;
- deployment dates;
- time since publication;
- recency decay;
- cost of delaying action; or
- the severity of the trigger.

It measures `urgent_signal_share`, not actual time urgency.

---

# 8. Priority feature

## 8.1 Intended business meaning

Priority is intended to order opportunities for analyst attention.

## 8.2 Exact formula

```text
Priority = 0.40 × Attractiveness
         + 0.35 × Orange fit
         + 0.15 × Confidence
         + 0.10 × Urgency
```

## 8.3 Why these weights were chosen

The MVP prioritizes:

1. external evidence first;
2. Orange capability alignment second;
3. evidence support third; and
4. urgent triggers fourth.

The weights sum to one, which keeps the result on a 0–100 scale.

## 8.4 Worked example

For the Public/Gov compliance opportunity:

```text
Attractiveness = 76.2
Orange fit     = 100.0
Confidence     = 89.2
Urgency        = 28.6

Priority = 0.40 × 76.2
         + 0.35 × 100.0
         + 0.15 × 89.2
         + 0.10 × 28.6

Using the displayed one-decimal components:

         ≈ 30.48 + 35.00 + 13.38 + 2.86
         ≈ 81.72

The code calculates with the unrounded component values and stores 81.7 after
final rounding.
```

## 8.5 Correct interpretation

Correct statement:

> Under the current MVP weights, this opportunity ranks highly for analyst
> attention.

Incorrect statement:

> The opportunity has an 81.7% probability of success.

## 8.6 Statistical weakness: overlapping variables

Source quality and source breadth appear in attractiveness and again in
confidence. Priority therefore indirectly weights them more than the displayed
15% confidence weight suggests.

Orange fit can also be inflated by contextual keyword groups. The priority score
inherits that weakness.

The priority formula should be sensitivity-tested before stakeholder adoption.

---

# 9. Radar / Watchlist feature

## 9.1 Exact publication gate

An opportunity is `RADAR` only if:

```text
distinct event keys >= 2
distinct source names >= 2
confidence score >= 45
```

Otherwise it becomes `WATCHLIST`.

## 9.2 Why this method was chosen

The gate prevents a single article or single source from becoming a published
Radar recommendation, even when its priority score is high.

## 9.3 Example

The Public/Gov compliance opportunity has:

```text
7 event keys
5 source names
89.2 confidence
```

It passes all three conditions and receives `RADAR` status.

## 9.4 Limitation

The threshold values 2, 2 and 45 are MVP governance rules, not thresholds
validated against historical Orange decisions.

---

# 10. Market-potential feature

## 10.1 Intended business meaning

The intended question is:

> What annual service value could be addressable for this opportunity under
> stated customer-population, adoption and engagement-value assumptions?

The code calls this market potential. It should not be presented as expected
Orange revenue.

## 10.2 Evidence actually used

### A. Enterprise population

Source:

```text
Eurostat Structural Business Statistics
```

Measured variables:

```text
country
NACE activity
enterprise size class
number of enterprises
```

This provides the potential organizational customer base.

### B. Technology-adoption proxy

Source:

```text
Eurostat Digital Economy and Society indicators
```

Current proxies:

| Technology family | Indicator meaning | Year |
|---|---|---:|
| AI | Enterprises using any AI technology | 2025 |
| Cloud | Intermediate or sophisticated paid cloud use | 2025 |
| Cybersecurity | Enterprises using at least one ICT security measure | 2024 |
| IoT | Enterprises using IoT | 2021 |

The percentage is converted to a rate between 0 and 1.

### C. Annual engagement value

The intended evidence is validated comparable awarded contracts:

```text
low annual EUR value
central annual EUR value
high annual EUR value
```

Greenfield and expansion/managed-service scenarios use separate annual values.

## 10.3 Implemented mappings

Only these vertical mappings currently exist:

```text
Manufacturing → NACE C
Automotive    → NACE C29
```

Implemented technology proxies are:

```text
machine learning, computer vision, NLP → AI
cloud data platform, edge, digital twin → Cloud
cybersecurity platform → Cybersecurity
IoT, RFID, robotics, autonomous vehicles/drones → IoT
```

Other verticals and technologies are explicitly unavailable.

## 10.4 Exact formulas

For one country-size cell:

```text
N = enterprise count
a = adoption rate from 0 to 1

Greenfield addressable enterprises = N × (1 − a)
Expansion addressable enterprises  = N × a
```

For approved annual values:

```text
Greenfield potential = greenfield enterprises × greenfield annual value
Expansion potential  = expansion enterprises × expansion annual value

Opportunity potential = sum across country cells and both scenarios
```

The calculation is repeated for low, central and high annual values.

## 10.5 Why this method was chosen

The bottom-up structure is explainable:

```text
number of possible organizational buyers
× plausible annual service value per buyer
```

Adoption divides the population into:

- non-adopters that may require a new implementation; and
- adopters that may require expansion, integration, security or managed service.

Separate scenario values avoid assuming both customer types buy the same
engagement.

## 10.6 Hypothetical example — not a current output

Assume only for demonstration:

```text
N = 10,000 enterprises
a = 40% = 0.40
greenfield central annual value = €20,000
expansion central annual value = €8,000
```

Then:

```text
Greenfield enterprises = 10,000 × (1 − 0.40) = 6,000
Expansion enterprises  = 10,000 × 0.40       = 4,000

Greenfield potential = 6,000 × €20,000 = €120,000,000
Expansion potential  = 4,000 × €8,000  = €32,000,000

Central annual addressable potential = €152,000,000
```

This does not mean Orange would earn €152 million. It assumes every addressable
enterprise buys one engagement at the selected annual value and does not deduct
competitor share, non-buyers, delivery limits, procurement friction or churn.

## 10.7 Validation gates

A EUR value is shown only when:

```text
vertical mapping exists
technology proxy mapping exists
enterprise count is non-negative
adoption rate is between 0 and 1
all annual values are present
0 <= low <= central <= high
currency = EUR
review_status = approved
calculated potential is non-negative
```

If validation fails, EUR values are cleared.

## 10.8 Current real result

```text
205 market-size records
205 pending_or_unavailable
0 validated EUR headlines
```

Reasons include missing approved annual values and missing vertical mappings.
For the Public/Gov worked example:

```text
vertical mapping = not_yet_mapped_to_eurostat_nace
annual assumption = missing
market-size status = pending_or_unavailable
```

No EUR value can currently be presented for that example.

---

# 11. What is implemented versus what is only proposed

| Item | Implemented now? | Evidence |
|---|---|---|
| Deterministic signal points | Yes | `05_score_opportunities.py` |
| Source-type priors | Yes | `04_enrich_candidates.py` |
| Attractiveness formula | Yes | `05_score_opportunities.py` |
| Time-based market momentum | No | Current code uses event count |
| Keyword-group Orange fit | Yes | `04b_auto_enrich_candidates.py`, `05_score_opportunities.py` |
| Orange-approved capability fit | No | Requires official capability validation |
| Right-to-win | No | Requires Orange and competitor evidence |
| Confidence index | Yes | `05_score_opportunities.py` |
| Statistical confidence interval | No | Not implemented |
| Urgent-signal percentage | Yes | `05_score_opportunities.py` |
| Deadline-based urgency | No | Not implemented |
| Radar/Watchlist gate | Yes | `05_score_opportunities.py` |
| Eurostat preparation | Yes | `07a`, `07b` |
| Market-potential formula | Yes | `07d_calculate_market_potential.py` |
| Approved market-size EUR outputs | No | All 205 currently unavailable |
| Beta-app market-size export | Yes | `07f_build_opportunity_market_size_export.py` |
| Final Beta-app integration | No | Planned after final branch integration |

---

# 12. How these measurements should be improved

## 12.1 Attractiveness

Add:

- actual procurement buyer count and validated award value;
- recent-versus-previous-period event growth;
- regulatory scope and effective date;
- named deployments and customer count;
- investment amount; and
- expert validation of component weights.

## 12.2 Orange fit

Remove contextual groups from the capability count. Use an official Orange
capability taxonomy and add:

- certifications;
- customer references;
- offering maturity;
- geographic delivery capacity;
- partner coverage; and
- strategic-priority weights.

## 12.3 Confidence

Add:

- source-owner independence;
- original-claim deduplication;
- expert agreement;
- sample-based error estimates; and
- confidence intervals where statistically justified.

Avoid counting the same source evidence twice inside priority.

## 12.4 Urgency

Add:

- days until regulatory deadline;
- days until tender close;
- recency decay;
- implementation lead time; and
- cost of delay.

## 12.5 Market potential

Add:

- validated NACE mappings for additional verticals;
- more vertical-specific adoption evidence;
- approved annual engagement values;
- realistic buyer-conversion rates;
- serviceable-market constraints;
- Orange capacity and geographic coverage; and
- sensitivity and uncertainty analysis.

---

# 13. Stakeholder-safe explanation

Use this statement:

> We currently use transparent evidence indices. Attractiveness summarizes signal
> strength, source breadth, source priors and event breadth. Orange fit summarizes
> provisional keyword-group alignment. Confidence summarizes evidence volume,
> source prior and source breadth. Urgency is the share of regulation, buying and
> market-move signals. Market potential is a separate bottom-up scenario using
> enterprise population, adoption proxies and approved annual engagement values.
> These measurements help prioritize analyst attention; they are not yet
> validated predictions of revenue or win probability.

Do not say:

- “Attractiveness proves market demand.”
- “Orange fit is right-to-win.”
- “Confidence is the probability that the opportunity is correct.”
- “Urgency measures the time remaining to act.”
- “Market potential is expected Orange revenue.”
- “The current model has validated EUR estimates.”

---

# 14. Source-of-truth files

```text
Analysis/04_enrich_candidates.py
Analysis/04b_auto_enrich_candidates.py
Analysis/05_score_opportunities.py
Analysis/07a_prepare_eurostat_sbs.py
Analysis/07b_prepare_eurostat_ict_adoption.py
Analysis/07c_prepare_comparable_contract_values.py
Analysis/07d_calculate_market_potential.py
Analysis/07f_build_opportunity_market_size_export.py

Analysis/outputs/enrichment/auto_scoring_candidates.csv
Analysis/outputs/scoring/opportunity_scores.csv
Analysis/outputs/scoring/opportunity_evidence.csv
Analysis/outputs/scoring/scoring_exclusions.csv
Analysis/outputs/scoring/scoring_summary.csv
Analysis/outputs/market_sizing/market_potential_scenarios.csv
Analysis/outputs/market_sizing/beta_opportunity_market_sizes.json
```

If this document and the code disagree, the current executable code and its
generated outputs are the implementation source of truth. Any change to a
formula must update the code, configuration, outputs, presentation and this
document together.
