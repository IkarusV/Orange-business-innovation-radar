# Analysis and opportunity-scoring workflow

This folder adds an auditable analytics layer to the team Innovation Radar. It does not replace the research collectors, taxonomy classifier, SQLite database, or Beta-app interface.

## Purpose

The team pipeline identifies potential opportunity spaces as `Vertical x Use Case x Technology`. This layer validates the classification and ranks only complete, past-dated evidence using separate scores for market attractiveness, Orange Business fit, evidence confidence, urgency, and combined priority.

These are transparent evidence indices. They are not market-size, revenue, ROI, or contract-win predictions.

## Folder contents

| File | Role |
|---|---|
| `01_audit_database.py` | Read-only schema, coverage, date and source audit of the supplied SQLite database. |
| `02_build_dataset.py` | Creates per-vertical article and candidate CSVs from the database. |
| `03_validate_classification.py` | Creates a small stratified human-validation sample and calculates initial classification metrics. |
| `04_enrich_candidates.py` | Adds source priors, date checks, event keys and enrichment review fields. |
| `04b_auto_enrich_candidates.py` | Applies transparent Orange-addressability and signal rules without an API call. |
| `05_score_opportunities.py` | Builds valid opportunity spaces and calculates scores, Radar and Watchlist status. |
| `analysis_config.json` | Vertical, source and candidate-selection configuration. |
| `KILO_ANALYSIS_HANDOFF.md` | Detailed pipeline, scoring and visualization specification. |
| `ENRICHMENT_AND_SCORING_CHANGELOG.md` | Rule and scoring changes made on 2026-08-25. |
| `BETA_AND_RESEARCH_PIPELINE_INTEGRATION.md` | How to adopt the outputs in `research-pipeline` and Beta-app. |

`06_visualize_results.py` is intentionally not included in the current workflow because the final interactive UX is expected to use Beta-app. Static charts can be added later from the final scoring CSVs.

## Inputs and boundaries

The research pipeline owns collection and classification. The Analysis layer must use a copy of the supplied database in read-only mode and must never overwrite `articles.db`.

### Beta-app branch contents

This Beta-app branch includes the portable market-sizing source, configuration,
prepared Eurostat reference tables, annual-value review template, scoring input,
and current market-size outputs. Large raw Eurostat downloads, SQLite databases,
per-vertical article exports, and manual enrichment-review files are deliberately
excluded. They are not needed to inspect or rerun `07d` and `07f` with the
included inputs.

To refresh the market-size export after changing approved annual-value
assumptions, run:

```powershell
.\.venv\Scripts\python.exe .\analysis2\07d_calculate_market_potential.py
.\.venv\Scripts\python.exe .\analysis2\07f_build_opportunity_market_size_export.py
```

Then copy the refreshed `analysis2/outputs/market_sizing/beta_opportunity_market_sizes.json`
and `.csv` into `imports/market_size/` and restart the app.

Do not commit databases, embeddings, `__pycache__`, raw intermediate per-vertical exports, or copied teammate repositories. They are either large, reproducible, or belong to another branch.

## Reproducible run order

Run from the Beta-app repository root after installing the standard requirements.
The market-size scripts require `pandas`, which is included in this repository's
`requirements.txt`.

```powershell
.\.venv\Scripts\python.exe .\analysis2\01_audit_database.py
.\.venv\Scripts\python.exe .\analysis2\02_build_dataset.py
.\.venv\Scripts\python.exe .\analysis2\03_validate_classification.py --mode create-sample
# Complete the human taxonomy labels in the created CSV.
.\.venv\Scripts\python.exe .\analysis2\03_validate_classification.py --mode evaluate
.\.venv\Scripts\python.exe .\analysis2\04_enrich_candidates.py --mode enrich-rules
.\.venv\Scripts\python.exe .\analysis2\04b_auto_enrich_candidates.py
.\.venv\Scripts\python.exe .\analysis2\05_score_opportunities.py
```

Close scoring CSVs in Excel before the last command because Windows locks open files.

## Scoring eligibility

An article can contribute to an opportunity score only when `vertical`, `use_case_id`, and `technology_id` are non-empty; `classification_status == classified`; `enrichment_status == ready_for_scoring`; and `date_quality_flag == valid_past`.

Every ineligible record is retained in `scoring_exclusions.csv` with a reason.

## Current pilot result

The current validated run produced:

```text
576 automatically relevant candidates
338 eligible complete evidence records
238 excluded records
205 valid opportunity spaces
44 Radar spaces
161 Watchlist spaces
```

The initial small stratified classification-validation pilot had 25 non-ambiguous human-evaluated rows, accuracy `0.92`, relevant precision `0.846`, recall `1.00`, and F1 `0.917`. This is a small pilot, not a claim of full-corpus model accuracy.

## Integration with the team branches

```text
research-pipeline database and classification
    -> Analysis enrichment and scoring
    -> opportunity_scores.csv + opportunity_evidence.csv
    -> Beta-app read adapter and existing UX
```

See `BETA_AND_RESEARCH_PIPELINE_INTEGRATION.md` for exact field mapping and ownership recommendations.
