# Innovation Radar Analysis Handoff for Kilo

## Objective

Build the remaining analysis stages for the Orange Business Innovation Radar.

The unit of analysis is:

```text
Vertical × Use Case × Technology
```

The code must support every vertical while Manufacturing remains the first methodology-validation example. Do not create separate programs per vertical.

## Workspace and safety rules

- Analysis root: `C:\BeCode_data\Orange-business-innovation-radar\Analysis`
- Source database: `C:\BeCode_data\Orange-business-innovation-radar\BeCode_dataOrange-radar-research-pipeline\data\articles_analysis.db`
- Treat the SQLite database as read-only. Do not change its schema or records.
- Do not modify `01_audit_database.py`, `02_build_dataset.py`, or `03_validate_classification.py` unless a compatibility bug makes it unavoidable.
- Write new outputs below `Analysis\outputs\`.
- Preserve source article IDs, URLs, titles, source types, pipeline labels, and original classifier fields in every downstream CSV.
- Use Python 3.12 and the existing project virtual environment where possible.

## Work completed

### 01: Database audit

`01_audit_database.py` was run read-only.

| Indicator | Result |
|---|---:|
| Articles | 20,285 |
| Article classifications | 11,140 |
| ML noise scores | 10,352 |
| Opportunity spaces in teammate database | 309 |
| Verticals | 14 |
| Duplicate URLs | 0 |
| Duplicate GUIDs | 0 |
| Orphan classifications | 0 |

Caveats:

- `client_relevance` is empty for every classification. The teammate pipeline performed taxonomy matching, not validated Orange Business addressability.
- 402 `published_date` values are later than 2026-08-25, mostly from CORDIS. They may be project start or event dates. Do not treat them as current article publications or current momentum.
- `classification_pool` contains records from selection dates 2026-08-22 and 2026-08-23. It is not one clean sampling run.
- The database has no per-article signal-type field.

### 02: Multi-vertical dataset build

`02_build_dataset.py` was run for all verticals. It reads the database and creates:

```text
Analysis\outputs\<vertical_slug>\articles.csv
Analysis\outputs\<vertical_slug>\candidate_queue.csv
```

`articles.csv` contains every article in the vertical. `candidate_queue.csv` contains pipeline statuses `classified` and `needs_review`.

There are 3,071 candidates. Do not require a human to read all 3,071.

| Vertical | Candidates |
|---|---:|
| Aerospace | 277 |
| Automotive | 185 |
| Defense | 227 |
| Energy | 356 |
| Finance, Banking, Insurance | 262 |
| Healthcare | 190 |
| Lifesciences | 110 |
| Manufacturing | 124 |
| Media & Entertainment | 152 |
| Natural Resources | 218 |
| Public/Gov sector | 203 |
| Retail | 171 |
| Transportation & Construction | 219 |
| Wholesale | 377 |

Current source columns:

```text
article_id, vertical, title, summary, url, source_name, source_type,
published_date, time_window, classification_status, use_case_id,
technology_id, classification_confidence, classification_evidence,
ml_usefulness_probability, ml_keep_recommended
```

### 03: Human validation of taxonomy classification

`03_validate_classification.py` generated and evaluated a 42-row stratified sample: one `classified`, one `needs_review`, and one `no_match` record for each of 14 verticals.

The reviewer completed `human_taxonomy_relevance`. Accepted values are `RELEVANT`, `IRRELEVANT`, `UNSURE`, and `REVIEW`; the two ambiguous values are excluded from binary metrics.

| Pilot metric | Result |
|---|---:|
| Finalized automatic decisions evaluated | 25 |
| Accuracy | 92.0% |
| Relevant precision | 84.6% |
| Relevant recall | 100.0% |
| Relevant F1 | 91.7% |
| Pipeline `needs_review` records | 14 |
| Human ambiguous records | 7 |

Confusion matrix:

| Actual / predicted | Relevant | Irrelevant |
|---|---:|---:|
| Relevant | 11 | 0 |
| Irrelevant | 2 | 12 |

Constraints:

- This is a small stratified pilot, not 92% accuracy for the full corpus.
- It measures taxonomy relevance, not Orange Business opportunity relevance.
- Pipeline `needs_review` is an abstention, not an automatically wrong prediction.

Existing validation outputs are in `Analysis\outputs\validation\`.

## Remaining implementation plan

## 04_enrich_candidates.py

### Purpose

Create a transparent evidence-enrichment dataset from the 3,071 candidate records. This stage bridges generic taxonomy matches to Orange-addressable opportunity evidence.

It must not claim every taxonomy match is an Orange opportunity.

### Inputs

- Every `Analysis\outputs\*\candidate_queue.csv`.
- `Analysis\outputs\validation\validation_sample.csv` for reference only; do not overwrite it.
- Optional source registry metadata. If unavailable, use explicit source-type priors and label them as priors.

### Required outputs

```text
Analysis\outputs\enrichment\all_candidates_base.csv
Analysis\outputs\enrichment\enriched_candidates.csv
Analysis\outputs\enrichment\enrichment_review_queue.csv
Analysis\outputs\enrichment\enrichment_summary.csv
```

### Preserve existing columns and add

```text
source_quality_prior
source_independence_group
source_role
date_quality_flag
signal_type
signal_confidence
orange_relevance
orange_relevance_confidence
orange_fit_basis
orange_relevance_rationale
event_key
event_key_method
enrichment_method
enrichment_status
review_status
```

Allowed values:

```text
signal_type:
regulation, buying_signal, market_trend, market_move,
technology_maturity, proof_signal, unknown

orange_relevance:
RELEVANT, IRRELEVANT, REVIEW

orange_fit_basis:
explicit, inferred, unsupported

source_role:
primary_institutional, primary_company, secondary_media, vendor, unknown

date_quality_flag:
valid_past, future_event, missing, invalid

enrichment_status:
ready_for_scoring, needs_review, excluded
```

### Enrichment rules

1. Mark a record `RELEVANT` only if this chain is plausible:

   ```text
   external event → business problem → digital B2B use case
   → technology/service need → credible Orange Business role
   ```

2. A generic manufacturing event, consumer story, or unrelated industrial incident is not automatically Orange-relevant.
3. `explicit` means the article names Orange/Orange Business. `inferred` means an Orange role is plausible but not named. `unsupported` means no credible Orange role is visible.
4. Future CORDIS/RSS dates must be flagged `future_event` and must not count as recent publication evidence.
5. A vendor announcement without a named customer, measurable deployment, procurement, regulation, or maturity milestone is supplementary/weak evidence.
6. Use these documented MVP source-quality priors where no better registry mapping exists:

   | Source type | Prior | Default role |
   |---|---:|---|
   | `ted` | 0.90 | primary_institutional |
   | `ocds_uk`, `ocds_ua` | 0.90 | primary_institutional |
   | `cordis` | 0.80 | primary_institutional |
   | `rss` | 0.55 | secondary_media |
   | `gnews` | 0.45 | secondary_media |

   These are quality priors, not market-size estimates or proof of truth.

7. Independence is not URL count. In the MVP use source-owner/source-type grouping when better ownership metadata is unavailable; document the limitation.
8. Start event keys conservatively. Exact canonical URL is safe. A fuzzy title grouping must be labelled `fuzzy_title` and remain reviewable.
9. Never silently overwrite human-entered enrichment values on rerun.

### Required modes

Implement explicit modes such as:

```text
--mode prepare
--mode enrich-rules
--mode import-reviewed
--mode summary
```

- `prepare`: combine and validate all candidate queues; create the base file once.
- `enrich-rules`: add deterministic/default fields such as quality priors and date flags. Do not invent Orange relevance with keywords alone.
- `import-reviewed`: merge a human/model-reviewed enrichment CSV by `article_id`, preserving original evidence.
- `summary`: write counts by vertical, signal type, Orange relevance, source role, and review status.

Any LLM/API enrichment must be optional, separately configured, batchable, traceable, and must save the prompt/model/method. The default workflow must work without an API key.

## 05_score_opportunities.py

### Purpose

Aggregate enriched evidence into opportunity spaces and calculate transparent deterministic scores. Do not use an LLM to perform arithmetic.

### Input eligibility

Read:

```text
Analysis\outputs\enrichment\enriched_candidates.csv
```

Only score records where:

```text
orange_relevance = RELEVANT
enrichment_status = ready_for_scoring
use_case_id is present
technology_id is present
```

Keep incomplete, `REVIEW`, and `IRRELEVANT` records in an exclusion/review output with a reason.

### Required outputs

```text
Analysis\outputs\scoring\opportunity_evidence.csv
Analysis\outputs\scoring\opportunity_scores.csv
Analysis\outputs\scoring\watchlist.csv
Analysis\outputs\scoring\scoring_exclusions.csv
Analysis\outputs\scoring\scoring_summary.csv
```

### Required opportunity-level fields

```text
vertical
use_case_id
technology_id
opportunity_id
distinct_article_count
distinct_event_count
independence_group_count
primary_evidence_count
recent_valid_event_count
previous_valid_event_count
signal_strength_score
source_independence_score
evidence_quality_score
momentum_score
attractiveness_score
orange_fit_score
orange_fit_status
confidence_score
horizon
radar_status
score_rationale
evidence_gaps
```

### Scoring principles

Keep four concepts separate:

```text
Market attractiveness = external demand/evidence
Orange fit = Orange Business capability/role evidence
Confidence = trust in the evidence base
Urgency/horizon = timing trigger
```

Do not put Orange fit inside market attractiveness. Do not use raw article count as market size.

### Proposed MVP formula

```text
Attractiveness (0–100) =
30% signal strength
+ 25% source independence
+ 25% evidence quality
+ 20% momentum
```

All factors must be bounded to 0–100, stored separately, and described in the output.

Suggested signal weights for distinct events:

| Signal type | Weight |
|---|---:|
| regulation | 1.00 |
| buying_signal | 1.00 |
| proof_signal | 1.00 |
| technology_maturity | 0.75 |
| market_move | 0.70 |
| market_trend | 0.55 |
| unknown | 0.00 |

Use log-normalized event volume so high-volume or syndicated topics do not dominate:

```text
event_volume = min(log1p(distinct_event_count) / log1p(5), 1) × 100
signal_strength = event_volume × average_signal_weight
source_independence = min(independence_group_count / 3, 1) × 100
evidence_quality = average(source_quality_prior) × 100
```

For momentum, use valid past dates only. Compare a recent 180-day window with the preceding 180-day window. Future/missing/invalid dates must not raise momentum. With insufficient dated evidence, use a conservative value and document `insufficient_date_evidence`.

### Orange fit, confidence, and publication status

`orange_fit_score` is provisional and must not be presented as Orange-approved.

Suggested Orange-fit basis mapping:

| Basis | Base value |
|---|---:|
| explicit | 100 |
| inferred | 50 |
| unsupported | 0 |

Use an evidence-weighted average and label it `PROVISIONAL` unless explicit Orange evidence exists.

Suggested confidence formula:

```text
Confidence (0–100) =
30% evidence-event sufficiency
+ 30% independence sufficiency
+ 25% evidence quality
+ 15% review/validation support
```

Store thresholds and component values in a versioned config file, not hidden in code.

Suggested publication gates:

```text
Radar:
at least 2 distinct events
at least 2 independence groups
confidence >= 45

Watchlist:
all other spaces
```

Low-confidence spaces must not appear as ranked recommendations. Put them in `watchlist.csv` with specific evidence gaps.

## 06_visualize_results.py

### Purpose

Create reproducible decision-ready visuals from scored data. Do not add factual claims that are unsupported by the scored data.

### Inputs

```text
Analysis\outputs\scoring\opportunity_scores.csv
Analysis\outputs\scoring\watchlist.csv
Analysis\outputs\validation\validation_metrics.csv
Analysis\outputs\validation\confusion_matrix.csv
```

### Output folder

```text
Analysis\outputs\visualizations\
```

### Required visuals

1. `opportunity_scatter.png`
   - x-axis: attractiveness score
   - y-axis: provisional Orange-fit score
   - point size: confidence score
   - colour: Radar/Watchlist status
   - label only the top few opportunities.

2. `top_opportunities_bar.png`
   - Top 10 Radar opportunities by attractiveness.
   - Show confidence in label or colour.
   - Exclude Watchlist items from the ranked chart.

3. `use_case_technology_heatmap.png`
   - Use case × technology matrix.
   - Value: opportunity count or evidence-weighted attractiveness.
   - Support a vertical filter or save one chart per requested vertical.

4. `evidence_composition.png`
   - Source role or source-type composition for scored opportunities.
   - Make institutional versus supplementary evidence visible.

5. `validation_confusion_matrix.png`
   - Render the existing 2×2 matrix.
   - Clearly label it as a small stratified human-reviewed pilot.

6. `visualization_summary.csv`
   - Chart file, data source, row count, filters, and generation timestamp.

### Visualization rules

- Use `matplotlib` and/or `seaborn`.
- Do not use pie charts for evidence comparisons.
- Do not imply causality, market size, or commercial ROI from article counts.
- Add a footnote where relevant: `MVP evidence-based scores; not market-size estimates. Orange fit is provisional.`
- Save PNG and SVG where practical.
- Handle empty inputs gracefully: report a clear message instead of crashing or creating a misleading empty ranking.

## Definition of done

1. Files 04, 05, and 06 run from the project root using the existing environment.
2. They never modify the SQLite database.
3. They create the specified CSVs and visual files.
4. Every score is deterministic, bounded, documented, and traceable to stored evidence fields.
5. Orange fit, market attractiveness, confidence, and horizon remain separate.
6. Future-dated records do not increase momentum.
7. Review and excluded records remain traceable rather than disappearing.
8. The system can process Manufacturing, selected verticals, or every vertical without duplicate code.

## Recommended run order

```powershell
.\.venv\Scripts\python.exe .\Analysis\04_enrich_candidates.py --mode prepare
.\.venv\Scripts\python.exe .\Analysis\04_enrich_candidates.py --mode enrich-rules
# Complete or import reviewed enrichment decisions as available.
.\.venv\Scripts\python.exe .\Analysis\04_enrich_candidates.py --mode summary

.\.venv\Scripts\python.exe .\Analysis\05_score_opportunities.py
.\.venv\Scripts\python.exe .\Analysis\06_visualize_results.py
```

Do not score or visualize as if Orange relevance and signal type had been verified before enrichment is complete.

---

## Scoring mechanism: mathematical definition and interpretation

### What the scores are — and are not

The MVP uses a **transparent multi-criteria evidence index**. It ranks
opportunity hypotheses consistently; it does **not** predict revenue, market
size, probability of winning, or return on investment. All component scores
are bounded from 0 to 100 and must remain traceable to stored article-level
evidence.

The unit being scored is one:

```text
vertical × use_case_id × technology_id
```

For example:

```text
Manufacturing × predictive-maintenance × iot
```

The score must use only `ready_for_scoring` records with valid past dates.

### Article-level inputs

`05_score_opportunities.py` should receive the automatic scoring input where
available:

```text
Analysis\outputs\enrichment\auto_scoring_candidates.csv
```

The article-level fields needed are:

```text
article_id, event_key, vertical, use_case_id, technology_id,
source_name, source_independence_group, source_quality_prior,
signal_type, auto_positive_groups, published_date
```

Do not count duplicated `article_id` values twice. Use `event_key` to avoid
counting multiple copies of exactly the same event.

### Signal-strength scale

Convert `signal_type` to an ordinal evidence value. This is an explicit
business rule, not a learned probability.

| Signal type | Points (1–4) | Interpretation |
|---|---:|---|
| `regulation` | 4 | A compliance obligation can trigger action. |
| `buying_signal` | 4 | Tender, procurement, contract award, or stated budget. |
| `market_move` | 3 | Partnership, investment, acquisition, or deployment shows action. |
| `proof_signal` | 3 | Pilot, case study, or implemented solution demonstrates feasibility. |
| `technology_maturity` | 2 | A technology is becoming commercially usable. |
| `market_trend` | 2 | Directional evidence, but often broad or indirect. |
| `unknown` | 1 | No reliable signal type identified. |

```python
SIGNAL_POINTS = {
    "regulation": 4,
    "buying_signal": 4,
    "market_move": 3,
    "proof_signal": 3,
    "technology_maturity": 2,
    "market_trend": 2,
    "unknown": 1,
}
```

### 1. Market attractiveness (0–100)

Market attractiveness reflects external evidence only. It must not include
Orange fit or generic article volume.

```text
Attractiveness = Signal (0–30)
               + Independence (0–25)
               + Source quality (0–25)
               + Evidence momentum (0–20)
```

For one opportunity space:

```text
Signal component       = min(mean(signal_points) / 4, 1) × 30
Independence component = min(independent_source_count / 3, 1) × 25
Quality component      = min(mean(source_quality_prior), 1) × 25
Momentum component     = min(independent_event_count / 5, 1) × 20

attractiveness_score = sum of the four components
```

The `min(..., 1)` function is a **saturation cap**. Three independent sources
or five independent events are sufficient for the MVP to obtain the maximum
component score. This prevents one highly reported event from dominating the
ranking merely because it created many duplicate articles.

### 2. Orange fit (0–100)

Orange fit answers: *does the evidence match a capability Orange Business can
plausibly provide or integrate around?* It must not be described as a sales
probability or a guarantee that Orange will win.

Use the distinct capability groups extracted at enrichment:

```text
connectivity, cloud_edge, cybersecurity, data_ai,
industrial_operations, business_trigger
```

```text
orange_fit_score = min(distinct_capability_group_count / 4, 1) × 100
```

The cap means that four aligned capability groups are enough to show strong
MVP-level alignment. A later version should replace equal group weights with a
reviewed Orange Business capability map based on official evidence.

### 3. Confidence (0–100)

Confidence measures the quality of the conclusion, not its commercial value.

```text
Evidence-volume component = min(article_count / 5, 1) × 35
Quality component         = mean(source_quality_prior) × 35
Independence component    = min(independent_source_count / 3, 1) × 30

confidence_score = sum of the three components
```

Suggested interpretation:

| Confidence | Meaning |
|---:|---|
| 0–39 | Weak hypothesis; do not make a client recommendation. |
| 40–59 | Watchlist; collect more evidence. |
| 60–79 | Reasonable evidence base. |
| 80–100 | Strong MVP evidence across multiple quality sources. |

### 4. Urgency (0–100)

Urgency measures whether the evidence includes a near-term external trigger.
It is separate from attractiveness: a small regulation can be urgent, while a
large market trend can be less immediate.

```text
urgent_signals = {regulation, buying_signal, market_move}

urgency_score = (number of articles with an urgent signal / article_count) × 100
```

### 5. Combined priority (0–100)

The combined score ranks where to investigate first. Keep its components in
the output so users can disagree with the weights without losing the evidence.

```text
priority_score = 0.40 × attractiveness_score
               + 0.35 × orange_fit_score
               + 0.15 × confidence_score
               + 0.10 × urgency_score
```

The weights are a stakeholder assumption:

- 40% external opportunity strength;
- 35% Orange Business's potential right-to-win;
- 15% reliability of the evidence;
- 10% time pressure.

They must be stored as constants in the script and reported in the output
metadata. Do not present them as objectively learned statistical coefficients.

### Worked example

For an opportunity with four articles, two independent sources, three
independent events, mean source quality `0.75`, mean signal points `3.25`,
three distinct capability groups, and two urgent-signal articles:

```text
Attractiveness = (3.25 / 4 × 30) + (2 / 3 × 25) + (0.75 × 25) + (3 / 5 × 20)
               = 24.4 + 16.7 + 18.8 + 12.0 = 71.9

Orange fit     = (3 / 4) × 100 = 75.0
Confidence     = (4 / 5 × 35) + (0.75 × 35) + (2 / 3 × 30) = 74.3
Urgency        = (2 / 4) × 100 = 50.0

Priority       = (0.40 × 71.9) + (0.35 × 75.0) + (0.15 × 74.3) + (0.10 × 50.0)
               = 71.1 / 100
```

### Required scoring outputs

`opportunity_scores.csv` must include:

```text
opportunity_id, vertical, use_case_id, technology_id,
evidence_count, independent_source_count, independent_event_count,
average_source_quality, capability_groups,
attractiveness_score, orange_fit_score, confidence_score,
urgency_score, priority_score
```

`opportunity_evidence.csv` must retain the article-level evidence and the
opportunity ID that it supports. This is necessary for auditability and for
explaining a score to the team or client.

### Statistical safeguards and limitations

1. Scores are **indices**, not market-size or revenue estimates.
2. A source-quality prior is a relative evidence weight, not a claim that a
   source is a given percentage true.
3. Source independence is approximate. Different media sources can repeat the
   same press release; use `event_key` and independence groups to reduce this
   risk, and document the limitation.
4. Article counts must saturate and must never be interpreted as market size.
5. Automatic relevance is a first-pass classification. Use the existing
   human-reviewed validation sample to report its limitations.
6. Before client delivery, run a sensitivity check with reasonable alternative
   weights (for example, attractiveness 35–45% and Orange fit 30–40%). If the
   top opportunities change radically, report that the ranking is sensitive to
   the chosen weights.
