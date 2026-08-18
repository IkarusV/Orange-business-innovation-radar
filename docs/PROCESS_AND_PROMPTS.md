# Process and Prompt Record

## Repeatable research procedure

1. Register a source with name, URL, domain, geography, and enabled state.
2. Fetch and normalize its RSS/Atom items.
3. Deduplicate with GUID and canonical URL.
4. Send title, date, URL, and available article content to the extraction prompt.
5. Reject generic or unsupported opportunities.
6. Store the extracted claim with its original URL and date.
7. Group by normalized `Vertical x Use Case x Technology` identity.
8. Calculate deterministic scores with `config/scoring.json`.
9. Keep insufficient evidence on the watchlist.
10. Present evidence, rationale, confidence, and next action for human review.

## Prompt governance

Operational prompts live in `config/prompts.json`. Each has a version. Prompt changes should be committed with an explanation in `docs/DECISIONS.md`. Provider, endpoint, and model are runtime settings so the same procedure can be reproduced with another compatible model.

## Extraction contract

The extractor must return JSON containing relevance, vertical, use case, technology, geography, Orange domain, persona, signal type, evidence claim, urgency/horizon, narratives, factor values, and factor rationales. Missing required fields fail validation. Unsupported signal types fail validation.

## Signal taxonomy

- Regulation: law, policy, standard, compliance deadline.
- Buying signal: tender, procurement, budget, named buyer activity.
- Market trend: adoption data, forecast, repeated market demand.
- Market move: investment, acquisition, partnership, competitor action.
- Technology maturity: benchmark, certification, production readiness.
- Proof signal: named pilot, contract, deployment, measured outcome.

## Time horizon

- Now: binding deadline, active tender/buyer, or production proof with urgency.
- Next: visible momentum and likely demand within 12 to 24 months.
- Later: credible early signal with weak trigger, maturity, or evidence.

## Security record

API keys must never enter prompts, source files, SQLite, logs, screenshots, or Git. A key pasted into any conversation should be revoked and replaced.

## Full audit reference

See `docs/CLASSIFICATION_AND_SOURCE_AUDIT.md` for the code-level definitions, formulas, responsibility map, source behavior, limitations, and topic audit procedure.
