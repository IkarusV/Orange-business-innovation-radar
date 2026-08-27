# Market-size integration

## Purpose

The opportunity detail page can show an estimated annual addressable potential
in EUR for the exact combination:

```text
Vertical x Use case x Technology
```

Market size is not part of Attractiveness or Orange Fit. It is a separate
decision-support feature with its own evidence and validation state.

## Data flow

```text
analysis2 market-size pipeline
        |
        |  07f_build_opportunity_market_size_export.py
        v
imports/market_size/opportunity_market_sizes.json
        |
        |  exact key: vertical|use_case_id|technology_id
        v
market_size_repository.py
        |
        +--> opportunity detail card
        +--> focused-report context
```

The app keeps all of its opportunities. If a key is absent from the import, the
record is labelled unavailable rather than removed.

## Display safety rules

EUR is displayed only when all conditions pass:

1. export status is `estimated`;
2. low, central and high values are all present;
3. no value is negative;
4. `low <= central <= high`.

Otherwise the app shows `Estimate pending` or `Estimate unavailable` and the
blocking reason. Eurostat public expenditure, public employment, enterprise
counts, adoption proxies and TED buyer counts are never presented as market
size by themselves.

## Refresh procedure

After approved assumptions change, rerun the analysis2 calculation and export:

```powershell
& .\.venv\Scripts\python.exe .\analysis2\07d_calculate_market_potential.py
& .\.venv\Scripts\python.exe .\analysis2\07f_build_opportunity_market_size_export.py
```

Then copy these outputs into this app:

```text
analysis2/outputs/market_sizing/beta_opportunity_market_sizes.json
    -> imports/market_size/opportunity_market_sizes.json

analysis2/outputs/market_sizing/beta_opportunity_market_sizes.csv
    -> imports/market_size/opportunity_market_sizes.csv
```

Restart the app after refreshing the JSON because the repository caches the
index for the life of the Python process.
