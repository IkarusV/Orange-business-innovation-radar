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

---

## Eurostat reference-data preparation for market potential

### Why collect Eurostat data

Opportunity scoring ranks evidence and Orange Business fit; it does not measure commercial value in euros. Eurostat is used as a free, official and reproducible source for the enterprise denominator behind a later market-potential estimate.

It can establish how many medium and large manufacturing enterprises operate in the selected countries, how many operate in detailed activities such as automotive manufacturing, and the observed software-investment context in those industries.

Eurostat cannot directly report the euro market size of generative AI, cybersecurity, cloud, private 5G, or a specific Orange Business offer. A later model must therefore combine the enterprise denominator with an explicit technology-adoption proxy and a transparent annual engagement-value assumption.

```text
Market potential = addressable enterprise base × demand/adoption scenario × annual engagement-value assumption
```

This is a modelled estimate, not observed market revenue. A user interface must label it `estimated addressable annual potential`.

### Dataset roles

Four local Eurostat Structural Business Statistics downloads are prepared by one script. They must not be summed together because they describe different views of the same business population.

| Dataset | Relevant field | Role | Not for |
|---|---|---|---|
| `sbs_sc_ovw` | `ENT_NR` | Primary enterprise count by NACE and size class. | Direct technology market size. |
| `sbs_ovw_smc` | `ENT_NR` | Optional finer segmentation of large enterprises. | Primary total; current coverage is incomplete. |
| `sbs_ovw_act` | `ENT_NR` | Detailed vertical-to-NACE crosswalk validation. | Size-class denominator. |
| `sbs_ovw_iep` | `INV_SOFT_MEUR` | Older software-investment context and plausibility check. | Direct TAM/SAM. |

The geographic scope is now configured in `Analysis/market_geography_config.json`, not hardcoded in a script. It contains 29 countries grouped as France, Benelux, Germany, Southern Europe, DACH, UK & Ireland, Nordics and provisional Eastern Europe. Manufacturing is NACE `C`; Automotive is NACE `C29`; primary company sizes are `50-249` and `GE250`.

`C29` is a subset of `C`. Never add `C` and `C29` into one denominator. Use `C` for Manufacturing and `C29` for a separate Automotive vertical.

### `07a_prepare_eurostat_sbs.py`

Path: `Analysis/07a_prepare_eurostat_sbs.py`.

Purpose: read the four already-downloaded TSVs once and create small, normalised reference CSVs. It does not call an LLM, does not call an API, and does not change original Eurostat downloads.

Run from the project root:

```powershell
.\.venv\Scripts\python.exe .\Analysis\07a_prepare_eurostat_sbs.py
```

| Function | What it does |
|---|---|
| `find_year_column()` | Reads only the header and finds the requested year despite Eurostat header whitespace. |
| `read_and_normalise_dataset()` | Reads the compact dimension column plus one year, splits dimensions, extracts numeric values and preserves status flags. |
| `filter_relevant_rows()` | Keeps annual configured-country, NACE and indicator rows and attaches the configured Orange region. |
| `validate_coverage()` | Reports expected/found/numeric/missing rows and countries present. |
| `write_reference_table()` | Writes a compact standardised CSV while leaving raw downloads unchanged. |
| `main()` | Processes all four sources sequentially and writes a manifest. |

Eurostat stores multiple dimensions in its first column. Example: `A,ENT_NR,C,50-249,DE    14980 p` means annual number of enterprises in Manufacturing, 50-249 employees, Germany, numeric value `14980`, provisional flag `p`.

The script separates values from status flags. `p` means provisional, `e` estimated, `b` break in time series, and `:` missing or suppressed. Missing values remain missing and must never become zero.

### Outputs and current coverage

```text
Analysis/reference/eurostat/enterprise_counts_standard.csv
Analysis/reference/eurostat/enterprise_counts_extended.csv
Analysis/reference/eurostat/enterprise_counts_activity_validation.csv
Analysis/reference/eurostat/software_investment_context.csv
Analysis/reference/eurostat/preparation_manifest.csv
```

| Source | Year used | Numeric coverage | Decision |
|---|---:|---:|---|
| `sbs_sc_ovw` | 2024 | 105/108 | Primary enterprise denominator; 27 of 29 configured countries have rows. |
| `sbs_ovw_smc` | 2024 | 9/34 | Optional detail only; not primary. |
| `sbs_ovw_act` | 2024 | 54/54 | Validate detailed NACE mapping; 27 countries have rows. |
| `sbs_ovw_iep` | 2021 | 41/42 | Older software-investment context; not used in the denominator. |

`sbs_ovw_iep` uses 2021 because its selected `INV_SOFT_MEUR` values are suppressed in the 2022 and 2023 columns. Its older vintage must remain visible in any client output.

### Next market-sizing steps

1. Prepare Eurostat ICT-adoption data for AI, cloud, IoT and cybersecurity. **Completed by `07b_prepare_eurostat_ict_adoption.py`.**
2. Add an explicit technology-to-adoption-proxy crosswalk and flag proxy use.
3. Add annual engagement values from comparable contracts or declared assumptions, retaining low/base/high values and sources.
4. Calculate TAM/SAM ranges only for spaces with sufficient mapping coverage.
5. Keep observed public-procurement values as a separate floor, not as the same quantity as bottom-up market potential.
6. ECB enterprise-financing data may become an investment-context badge; do not multiply it directly into euro market-potential arithmetic.

### Comparable-contract preparation (Step 3)

Path: `Analysis/07c_prepare_comparable_contract_values.py`.

Purpose: create a public, auditable evidence layer for annual engagement-value assumptions. It links the already taxonomy-classified and scoring-ready articles to TED procurement notices in the local research database. It never writes to that database; it opens SQLite with `mode=ro`.

The database contains 6,957 TED notices and 4,125 notices with a positive stored `total_value` (59.3%). There are 368 Manufacturing notices with a stored positive value. This is useful comparable-contract evidence, but it is **not automatically Orange Business revenue, market size, or an annual value**.

#### What the script extracts

For each scoring-ready TED record, it writes `comparable_contract_observations.csv` with the opportunity taxonomy, raw notice value, CPV codes, buyer country, notice type, publication date, and the following safeguards:

- `is_award_notice`: true only for `can-*` contract-award notices.
- `value_observation_status`: separates an awarded observation from a contract notice that is only a demand signal.
- `currency_status`: records that the current TED collector did not store a currency.
- `annualisation_status`: records that the current collector did not store contract duration.

The current pipeline collected `total-value`, but did not preserve the currency or contract duration. Therefore the script labels the extracted number `total_contract_value_raw`, never `EUR`, and does not annualise it. This prevents an unsupported euro amount being displayed to Orange Business.

#### Statistical method

For an opportunity space with validated comparable awarded contracts, the future manual value estimate should use a distribution rather than one cherry-picked tender:

\[
Q_{25},\; Q_{50}=\operatorname{median}(x_1,\ldots,x_n),\; Q_{75}
\]

where each \(x_i\) is a validated, comparable contract value in the same currency and scope. The reported low, central and high comparable values are respectively the 25th percentile, median and 75th percentile. The median is preferred to the arithmetic mean because public-procurement values are highly right-skewed: a small number of very large frameworks would otherwise dominate the result.

The script requires at least five awarded observations before it creates a row in `annual_engagement_value_assumptions_template.csv`. Five is a minimum screening threshold, not proof of a stable market distribution; the sample size must remain visible in the UX and in client material. Spaces below the threshold remain evidence gaps rather than receiving invented values.

Once currency and duration have been validated from the original TED notice, annualisation is:

\[
\text{annual contract value}_i =
\frac{\text{validated total contract value}_i\;[EUR]}
     {\text{validated contract duration}_i\;[years]}
\]

Only then may the P25 / median / P75 range be stored as `low_annual_value_eur`, `central_annual_value_eur`, and `high_annual_value_eur`.

#### Economic interpretation

Comparable contracts are an **observed procurement benchmark**: evidence of what selected public buyers contracted for a sufficiently similar solution. They are not the same quantity as total addressable market (TAM), serviceable addressable market (SAM), an Orange revenue forecast, or a procurement floor across all countries.

The later bottom-up annual-potential calculation is kept separate:

\[
\text{estimated annual addressable potential} =
\text{addressable enterprise base} \times
\text{demand scenario} \times
\text{annual engagement-value assumption}
\]

TED comparables inform the final factor only after validation. Eurostat enterprise counts inform the first factor; ICT adoption data informs the scenario, with its sector-proxy limitation clearly stated. This separation avoids double-counting market evidence already present in the opportunity-attractiveness score.

Run from the project root:

```powershell
.\.venv\Scripts\python.exe .\Analysis\07c_prepare_comparable_contract_values.py
```

Outputs:

```text
Analysis/reference/market_sizing/comparable_contract_observations.csv
Analysis/reference/market_sizing/comparable_contract_summary.csv
Analysis/reference/market_sizing/annual_engagement_value_assumptions_template.csv
```

First local run against the current scoring-ready corpus produced 67 taxonomy-complete TED observations, of which 22 were awarded notices with a positive raw value, across 21 opportunity spaces. No space reached the minimum five comparable awarded observations. This is a valid result: the annual-assumptions template is intentionally empty rather than populated with weak estimates. The raw observations and their explicit evidence gaps remain available for future accumulation or targeted validation.

### Market-potential scenarios (Step 4)

Path: `Analysis/07d_calculate_market_potential.py`.

Purpose: combine the Step 1 enterprise denominator, Step 2 technology-adoption proxy, and Step 3 *reviewed* annual engagement value into an evidence-bounded euro scenario. It does not modify the database, scoring files or source evidence.

#### Inputs and crosswalks

The script reads:

| Input | Role in the calculation |
|---|---|
| `enterprise_counts_standard.csv` | Number of medium and large enterprises by country, NACE code and size class. |
| `technology_adoption_rates.csv` | Country/size ICT adoption rates; always marked as all-business proxy data. |
| `annual_engagement_value_assumptions_template.csv` | Human-reviewed low/central/high annual EUR assumptions only. |
| `opportunity_scores.csv` | The scored Vertical × Use Case × Technology spaces to which the model applies. |

Two deliberately narrow crosswalks are in the script. `Manufacturing -> C` and `Automotive -> C29` are the currently defensible vertical mappings. AI, cloud, cybersecurity and IoT-related technology IDs receive the corresponding adoption proxy. Technologies such as 5G, blockchain and warehouse automation are left unmapped because the available Eurostat data does not measure a defensible proxy for them. An unmapped item is a visible data gap, not a zero market.

#### Demand scenarios and formula

The script produces two scenarios for each mapped opportunity space and selected country/size cell:

\[
\text{greenfield buyer base} = N \times (1-a)
\]

\[
\text{expansion / managed-service buyer base} = N \times a
\]

where \(N\) is the Eurostat enterprise count and \(a\) is the relevant adoption rate. The first estimates enterprises that may not yet use the measured technology; the second estimates existing users that may buy integration, security, managed service, upgrade, or scale-out work. Adoption is not automatically demand, so these are scenarios rather than observations of sales intent.

For each scenario, potential is calculated only with an approved annual value:

\[
\text{low / central / high annual potential} =
\left(\sum \text{addressable enterprise base}\right) \times
\text{low / central / high annual engagement value [EUR]}
\]

The output uses low, central and high values rather than a single precise number so its uncertainty is visible. The user must set all three annual values and change `review_status` to `approved` in the Step 3 template before any euro estimate is emitted.

#### Geography, Europe totals and coverage safeguard

The model now calculates country-level cells first, then aggregates them into the configured Orange Business regions and a Europe-total row:

\[
\text{regional potential} = \sum_{c \in region}
\left(N_c \times d_c \times V\right)
\]

The outputs carry `geography_level` (`country`, `region`, or `europe`), `geography_id`, `geography_label`, `countries_with_source_data`, `expected_country_count`, and `country_coverage_status`. A partial regional or Europe total must be labelled with its coverage, rather than described as the whole of Europe.

The configured scope contains 29 countries. The local 2024 SBS denominator currently has source rows for 27; ICT adoption data currently has rows for 25. In practice, UK, Israel, Switzerland and Iceland require particular availability checks depending on the source. Missing source rows are treated as coverage gaps, never as zero enterprises or zero adoption.

This is an Orange Business Europe scope and still not a universal global TAM. It becomes a client-specific SAM when Orange confirms the exact countries, customer sizes and eligibility criteria. Rest-of-world continent estimates should be added only with separate, comparable denominators and adoption data.

Every output row has a `market_potential_status`:

- `estimated_proxy_based`: all mappings and a reviewed annual value exist.
- `not_estimable_missing_validated_annual_value`: evidence exists but the value assumption is not approved.
- `not_estimable_vertical_mapping_gap` or `not_estimable_technology_proxy_gap`: the available official data does not support the mapping.

This is the intended behaviour. A blank euro figure tells the stakeholder precisely what evidence needs improving, instead of presenting a misleading market-size number.

#### Market-size validation gate

Before a value is eligible for display as EUR, `07d_calculate_market_potential.py` applies these non-negotiable checks:

\[
N \geq 0,\quad 0 \leq a \leq 1,\quad 0 \leq V_{low} \leq V_{central} \leq V_{high}
\]

`N` is the enterprise count, `a` the adoption/demand rate, and `V` the annual engagement value. Currency must be explicitly `EUR`, and the annual-value row must have `review_status = approved`. Because all multiplication inputs are non-negative, a valid market-potential result cannot be negative.

An invalid value is never converted into a negative market-size display. The script assigns a `not_estimable_*` status, clears any invalid calculated value, and writes `market_sizing_validation_report.csv`. This report records the opportunity key, scenario, assumption status, currency, invalid enterprise/adoption-cell counts, and calculated values. The Beta-app should display a EUR figure only when `validation_status = passed` and `market_potential_status = estimated_proxy_based`.

Run from the project root:

```powershell
.\.venv\Scripts\python.exe .\Analysis\07d_calculate_market_potential.py
```

Outputs:

```text
Analysis/outputs/market_sizing/market_potential_scenarios.csv
Analysis/outputs/market_sizing/market_potential_summary.csv
Analysis/outputs/market_sizing/market_sizing_validation_report.csv
```

### Observed procurement benchmark (Step 5)

Path: `Analysis/07e_calculate_procurement_benchmark.py`.

Purpose: report what has been observed in the taxonomy-linked TED procurement evidence without confusing it with the Step 4 bottom-up annual-potential scenario. The script reads the Step 3 contract-observation file and the opportunity-score output; it does not call an API and does not change the database.

For every scored opportunity space, it reports the number of linked TED notices, awarded notices, notices with a positive stored raw value, awarded notices with a positive raw value, recency over the last 730 days, and—where possible—P25, median and P75 of awarded raw values.

\[
Q_{25},\; Q_{50},\; Q_{75}
= \operatorname{quantile}(\text{positive values of linked award notices})
\]

These statistics describe the distribution of observed comparable procurement values. They are not summed across notices, because notices may overlap, be frameworks, use different scopes, or cover multiple lots. They are not multiplied by the enterprise base, because that would double-count the separate economic concept measured in Step 4.

The raw benchmark has two binding limitations: the current TED collector did not retain currency, and it did not retain contract duration. Therefore the file uses `raw_award_value_*`, `currency_status`, and `annualisation_status`; it must not be displayed as euro market size or annual value. Its correct initial UX label is **“Observed comparable public-procurement evidence — currency validation pending.”**

The output status makes absence and quality explicit:

- `raw_award_values_currency_and_duration_unvalidated`: observed award values exist but need validation.
- `observed_notices_no_awarded_positive_value`: related notices exist, but no usable awarded raw value is stored.
- `no_taxonomy_linked_ted_observation`: no linked TED notice is currently in the scoring-ready corpus.

Run from the project root:

```powershell
.\.venv\Scripts\python.exe .\Analysis\07e_calculate_procurement_benchmark.py
```

Outputs:

```text
Analysis/outputs/market_sizing/procurement_benchmark.csv
Analysis/outputs/market_sizing/procurement_benchmark_summary.csv
```

### Eurostat ICT-adoption preparation (completed Step 2)

Path: `Analysis/07b_prepare_eurostat_ict_adoption.py`.

Purpose: normalise free, official Eurostat enterprise ICT-use data into rates that can later be matched to the prepared enterprise counts. This is required because the SBS files answer *how many potential buyers exist*, while ICT data answers *how widely a technology is already used*.

```text
Enterprise base × demand/adoption scenario × annual engagement value
```

The script does not call an LLM or an API. It reads the four downloaded, cached TSV archives under `Analysis/raw/eurostat/`, reads only one required year column from each, and writes one small reusable table. Downloading/caching the source files means rerunning the preparation requires no token usage and no network request.

| Technology proxy | Downloaded Eurostat source | Selected indicator | Year | Why this indicator is used |
|---|---|---|---:|---|
| AI | `isoc_eb_ai` | `E_AI_TANY` | 2025 | Enterprises using any AI technology; a broad AI proxy, including but not limited to generative AI. |
| Cloud | `isoc_cicce_use` | `E_CC1_SI` | 2025 | Enterprises using intermediate or sophisticated paid cloud services; more Orange-addressable than basic cloud use. |
| Cybersecurity | `isoc_cisce_ra` | `E_SECMGE1` | 2024 | Enterprises using at least one ICT security measure; an existing-security-maturity proxy, not a count of cyber incidents. |
| IoT | `isoc_eb_iot` | `E_IOT1` | 2021 | Enterprise IoT use proxy. It is the latest complete selected rate, but its older vintage requires a wider uncertainty band later. |

All sources are public Eurostat enterprise datasets. They were downloaded because they give country- and size-class-specific adoption rates for the selected Orange-relevant markets without using paid research or LLM-generated figures.

### Important proxy limitation

All four downloaded ICT datasets have `C10-S951_X_K` as the available NACE aggregate in the selected records: all non-financial business activities, rather than Manufacturing alone. Therefore the values are observed Eurostat rates for the all-business aggregate but must be labelled `basis = proxy` when applied to Manufacturing, Automotive, or another specific vertical.

Do not describe them as Manufacturing adoption rates. The output records the exact source NACE code and a `proxy_reason` for every row. A proxy should widen uncertainty; it must not silently change a market-potential base estimate.

### Normalisation details

`07b_prepare_eurostat_ict_adoption.py` uses:

| Function | What it does |
|---|---|
| `find_year_column()` | Reads the TSV header and resolves a requested year despite trailing whitespace. |
| `read_indicator()` | Reads the compact dimensions plus one year from a gzip TSV, extracts a numeric percentage and preserves Eurostat status flags. |
| `filter_and_standardise()` | Keeps annual `PC_ENT` rows for BE, DE, ES, FR, NL; size classes `50-249` and `GE250`; and the selected technology indicator. It converts percentages to a 0–1 `adoption_rate` and attaches source/proxy metadata. |
| `validate_coverage()` | Reports expected, found, numeric and missing rows so missing data is never mistaken for zero adoption. |
| `main()` | Combines the four technology proxies into a single reference table and manifest. |

Run from the project root:

```powershell
.\.venv\Scripts\python.exe .\Analysis\07b_prepare_eurostat_ict_adoption.py
```

Outputs:

```text
Analysis/reference/eurostat/technology_adoption_rates.csv
Analysis/reference/eurostat/ict_adoption_preparation_manifest.csv
```

### Geographic-scope update: Orange Business Europe

The earlier five-country reference below is a completed technical pilot and is superseded by `Analysis/market_geography_config.json`. The configuration contains 29 countries grouped as France, Benelux, Germany, Southern Europe, DACH, UK & Ireland, Nordics and provisional Eastern Europe. France is its own region because it is the home market and headquarters location of Orange. `Analysis/market_geography.py` loads this configuration for `07a`, `07b` and `07d`; editing the JSON changes country membership without changing calculation code.

The current expanded local-data coverage is:

| Data layer | Configured country/size cells | Rows found | Numeric values | Interpretation |
|---|---:|---:|---:|---|
| SBS enterprise denominator | 116 | 108 | 105 | Source rows for 27 of 29 configured countries. |
| AI adoption proxy | 58 | 50 | 50 | 25 countries x two size classes. |
| Cloud adoption proxy | 58 | 50 | 49 | One available row has no numeric value. |
| Cybersecurity adoption proxy | 58 | 50 | 50 | 25 countries x two size classes. |
| IoT adoption proxy | 58 | 50 | 49 | One available row has no numeric value. |

The revised `07d_calculate_market_potential.py` produces country, Orange-region and Europe-total rows. It calculates country cells first and then aggregates:

\[
\text{regional potential} = \sum_{c \in region} (N_c \times d_c \times V)
\]

Every row includes `geography_level`, `geography_id`, `geography_label`, `countries_with_source_data`, `expected_country_count`, `country_coverage_ratio`, and `country_coverage_status`. Missing source data is excluded from arithmetic and reported as `partial` or `no_country_data`; it is never converted to zero. The Beta-app should display Europe totals only together with this coverage information.

### Opportunity-space-first market size and Beta-app export

The primary commercial object is now the opportunity space:

\[
O = \text{Vertical} \times \text{Use Case} \times \text{Technology}
\]

Geography is calculated underneath that object. A country is a calculation cell, an Orange region is an optional drill-down, and the configured Europe total is the headline scope for the opportunity-space page. Regions must not become separate opportunity spaces.

#### Separate greenfield and expansion economics

`07c_prepare_comparable_contract_values.py` now creates six annual-value fields instead of one shared range:

```text
greenfield_low_annual_value_eur
greenfield_central_annual_value_eur
greenfield_high_annual_value_eur
expansion_low_annual_value_eur
expansion_central_annual_value_eur
expansion_high_annual_value_eur
```

This avoids assuming that a new implementation and an expansion or managed-service engagement have the same annual contract value. The row also requires explicit `currency = EUR` and `review_status = approved`.

For country \(c\), enterprise count \(N_c\), and adoption proxy \(a_c\):

\[
G_c = N_c(1-a_c)
\]

\[
E_c = N_ca_c
\]

where \(G_c\) is the greenfield enterprise base and \(E_c\) the expansion/managed-service enterprise base. Europe segment estimates are:

\[
M_G = \sum_c G_c \times V_G
\]

\[
M_E = \sum_c E_c \times V_E
\]

The opportunity-space headline range is emitted only when both non-overlapping segments pass validation:

\[
M_O = M_G + M_E
\]

Low, central and high totals are added like-for-like. If only one segment is valid, the export says `partial_estimate` and does not publish a total EUR headline. If neither is valid, it says `pending_or_unavailable` and all headline EUR values remain null.

#### Statistical validation

For each segment:

\[
0 \leq V_{low} \leq V_{central} \leq V_{high}
\]

Enterprise counts must be non-negative, adoption rates must be between zero and one, currency must be EUR, and the assumption must be approved. A negative or non-passing result is cleared before export. Missing Eurostat cells reduce `country_coverage_ratio`; they never become zero observations.

#### `07f_build_opportunity_market_size_export.py`

Path: `Analysis/07f_build_opportunity_market_size_export.py`.

The script reads the validated Step 4 scenario output and writes one record per opportunity space. The stable Beta-app join key is:

```text
vertical|use_case_id|technology_id
```

Each JSON record contains the Europe headline, both demand segments, country coverage, regional drill-downs and a display rule. The AI does not calculate values in this step; it receives deterministic, validated facts.

Run:

```powershell
.\.venv\Scripts\python.exe .\Analysis\07f_build_opportunity_market_size_export.py
```

Outputs:

```text
Analysis/outputs/market_sizing/beta_opportunity_market_sizes.json
Analysis/outputs/market_sizing/beta_opportunity_market_sizes.csv
```

Current run produced 205 opportunity-space records. All currently have `pending_or_unavailable` because no annual engagement-value assumption has yet passed the approval gate. This is expected and prevents the Beta-app or its report-generating AI from inventing an EUR value.

#### Beta-app and report-AI contract

The Beta-app should load the JSON through a market-size service and join it to an opportunity by the stable taxonomy key. It may show the Europe low/central/high EUR range only when `market_size.status = estimated`. Otherwise it should show the segment status, enterprise base, country coverage and missing-evidence reason.

The same structured record should be passed to report generation. When status is not `estimated`, the report context must include the instruction `Do not infer or invent a monetary market-size value`. The AI may explain validated data; it must not replace the deterministic calculation or validation gate.

Current coverage is complete: 10 numeric rows per technology proxy (five countries × two size classes), or 40 rows total. The output keeps `technology_proxy`, `source_dataset`, `indicator`, `year`, `country`, `source_nace_code`, `size_class`, `adoption_rate_percent`, `adoption_rate`, `basis`, `proxy_reason`, `status_flag`, and `raw_value`.
