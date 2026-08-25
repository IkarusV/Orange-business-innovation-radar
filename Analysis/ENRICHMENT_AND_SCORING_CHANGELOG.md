# Enrichment and scoring change log

Date: 2026-08-25  
Scope: `04b_auto_enrich_candidates.py` and `05_score_opportunities.py`

## Why these changes were made

The first automatic enrichment run was intentionally broad. It marked some provisional taxonomy records as relevant and used generic words as signal matches. That is suitable for a shortlist, but not strict enough for client-facing opportunity scores.

The pipeline now separates these stages:

```text
Automatic shortlist -> strict eligible evidence -> scored opportunity spaces
```

An opportunity space is valid only when it has all three fields: `Vertical x Use Case x Technology`.

## Changes in `04b_auto_enrich_candidates.py`

### Regulation matching is now explicit

Removed these regulation keywords: `act` and `standard`.

Reason: they are ambiguous. A TED record can contain `cn-standard`, which is a notice-type label, not regulatory evidence. The substring `act` can also occur inside unrelated words.

The remaining regulation phrases are `regulation`, `regulatory`, `directive`, `legislation`, `compliance requirement`, `legal requirement`, `policy mandate`, and `ai act`.

The row-level `enrichment_method` value changed from `transparent_rules_v1` to `transparent_rules_v2`, so every automatic decision records the rule version used.

Rerunning the file refreshes:

```text
outputs/enrichment/auto_enriched_candidates.csv
outputs/enrichment/auto_review_queue.csv
outputs/enrichment/auto_scoring_candidates.csv
outputs/enrichment/auto_enrichment_summary.csv
```

## Changes in `05_score_opportunities.py`

### Strict scoring eligibility

Only a record with non-empty `vertical`, `use_case_id`, and `technology_id`, plus `classification_status == classified`, `enrichment_status == ready_for_scoring`, and `date_quality_flag == valid_past`, can contribute to a score.

Reason: incomplete or provisional taxonomy cannot form a valid opportunity space, and future-dated records must not become historical market evidence.

### Exclusion audit trail

Ineligible records are retained in `outputs/scoring/scoring_exclusions.csv`. Reasons include `incomplete_taxonomy`, `taxonomy_not_classified`, `not_ready_for_scoring`, and `date_not_valid_past`.

### Duplicate protection and score components

Duplicate `article_id` values are removed before scoring so one article cannot inflate evidence count or scores. The script calculates the bounded scores `attractiveness_score`, `orange_fit_score`, `confidence_score`, `urgency_score`, and `priority_score`.

It also exposes `signal_component`, `independence_component`, `quality_component`, and `momentum_component`, making the attractiveness score auditable.

### Publication gate

An opportunity receives `publication_status = RADAR` only when it has at least two independent events, two independent sources, and confidence of at least 45. Other scored spaces remain `WATCHLIST` items.

### Output files

```text
outputs/scoring/opportunity_scores.csv
outputs/scoring/opportunity_evidence.csv
outputs/scoring/watchlist.csv
outputs/scoring/scoring_exclusions.csv
outputs/scoring/scoring_summary.csv
```

## Required run order

Close any scoring CSV files in Excel before running because Excel locks them on Windows.

```powershell
.\.venv\Scripts\python.exe .\Analysis\04b_auto_enrich_candidates.py
.\.venv\Scripts\python.exe .\Analysis\05_score_opportunities.py
```

Only after inspecting `opportunity_scores.csv` and `scoring_summary.csv` should the team create static charts or connect the data to the Beta-app interface.

## Interpretation limitation

These scores are transparent evidence indices. They do not predict market size, revenue, return on investment, or Orange Business's probability of winning a deal. The weights are explicit stakeholder assumptions and should be tested by sensitivity analysis before client delivery.
