# Integrating the scoring layer with the team branches

## Branch roles

| Branch | Current responsibility | What it does not yet provide |
|---|---|---|
| `research-pipeline` | Collects TED, CORDIS and OCDS evidence; applies ML filtering; classifies into `Vertical × Use Case × Technology`; stores `articles.db`. | A defensible opportunity-priority model based on attractiveness, Orange fit, confidence, urgency and source independence. |
| `Beta-app` | Provides the Reflex user interface, filters, opportunity cards, evidence pages, company workspace and reports. | It currently derives display relevance/confidence largely from article counts rather than the scoring outputs. |
| `feature/alecdocuments` / `Analysis` | Validates classifications, applies transparent enrichment, filters complete evidence, calculates auditable opportunity scores. | A production adapter inside the Reflex application. |

## Compatibility conclusion

The scoring work is adoptable by both branches. It should be added as a
separate analysis/scoring layer; it must not overwrite the collectors,
classifier, taxonomy, source database, or Reflex visual design.

```text
research-pipeline articles.db
        -> classification output
        -> Analysis enrichment and scoring
        -> opportunity_scores.csv + opportunity_evidence.csv
        -> Beta-app read adapter
        -> Ikarus's existing user interface
```

## What the scoring layer consumes

The scoring scripts use exported evidence rows and write CSV artefacts. They
do not modify `articles.db`.

Required input fields are:

```text
article_id, vertical, use_case_id, technology_id,
classification_status, date_quality_flag, enrichment_status,
event_key, source_name, source_quality_prior, signal_type,
auto_positive_groups
```

The final scored output is:

```text
Analysis/outputs/scoring/opportunity_scores.csv
Analysis/outputs/scoring/opportunity_evidence.csv
Analysis/outputs/scoring/watchlist.csv
Analysis/outputs/scoring/scoring_exclusions.csv
Analysis/outputs/scoring/scoring_summary.csv
```

## Research-pipeline adoption

The research branch currently aggregates `opportunity_spaces` by classified
article count and optional `avg_client_relevance`. Keep that schema unchanged
for the collector/classifier pipeline.

Recommended first integration:

1. Run the existing research pipeline normally.
2. Export its classified evidence into the Analysis input shape.
3. Run enrichment and `05_score_opportunities.py` as a post-processing step.
4. Treat the scoring CSVs as the ranked analytical artefact.

This avoids changing the SQLite schema before the scoring method is accepted
by the team.

## Beta-app adoption

Beta-app currently reads `opportunity_spaces` in:

```text
radar_v2/services/team_repository.py
```

Its current display logic approximates relevance from article count and
approximates confidence from article count. Replace only that read/mapping
layer with a CSV or database adapter for `opportunity_scores.csv`.

Suggested field mapping:

| Beta-app field | Scoring output field | UI label recommendation |
|---|---|---|
| `relevance` | `priority_score` | Priority score |
| `confidence` | `confidence_score` | Evidence confidence |
| `article_count` | `evidence_count` | Evidence records |
| `horizon` | Derived from `urgency_score` | Urgency: Now / Next / Later |
| opportunity ordering | `priority_score` descending | Priority ranking |
| detail-page evidence | `opportunity_evidence.csv` by `opportunity_id` | Supporting evidence |
| portfolio filter | `publication_status` | Radar / Watchlist |

Do not label `priority_score` as market size, commercial ROI, or probability of
winning. The UI should show the component scores or a tooltip explaining that
they are evidence-based indices.

## Recommended integration work split

| Owner | Task |
|---|---|
| Alec / analytics | Maintain enrichment rules, scoring weights, validation, output definitions and data-quality checks. |
| Research-pipeline owner | Keep collection, taxonomy classification, database refresh and data export stable. |
| Ikarus / Beta-app owner | Add a read-only scoring-output adapter and display priority, confidence, attractiveness, Orange fit and evidence links in the existing UX. |

## Merge safety

Do not copy the entire `Analysis` directory into `Pipelineteamfile/` blindly.
Beta-app deliberately nests a copy of the research pipeline in
`Pipelineteamfile/`, whereas `research-pipeline` keeps its pipeline folders at
repository root. Add the scoring scripts at repository root or package them as
a dedicated module, then set paths through configuration.

The first safe deliverable is this commit's scoring code and documentation.
The second, separate deliverable should be a small Beta-app adapter pull
request after Ikarus confirms where generated scoring artefacts will be stored
in development and deployment.
