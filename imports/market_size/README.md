# Opportunity market-size import

This folder contains the UI-facing export produced by the isolated `analysis2`
market-size pipeline.

- `opportunity_market_sizes.json` is the runtime source used by the Beta app.
- `opportunity_market_sizes.csv` is the auditable flat export for analysts.
- The stable join key is `vertical|use_case_id|technology_id`.
- A euro range is displayed only when the export status is `estimated` and the
  low, central and high values are non-negative and correctly ordered.
- Pending, unsupported and unmatched opportunities remain visible. The app
  explains the evidence gap instead of inventing a market value.

The source pipeline remains in `analysis2`; refresh these two files after
rerunning `07f_build_opportunity_market_size_export.py`.
