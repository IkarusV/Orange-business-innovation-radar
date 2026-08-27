# Analysis2 Market-Size Expansion Notes

## Purpose

`analysis2/` is a complete safety copy of `Analysis/`. The original folder was
not modified during this market-size expansion. All experimental changes and
new outputs described below exist only inside `analysis2/`.

## Why the original version covered only two verticals

The original files hard-coded:

```python
TARGET_NACE_CODES = ["C", "C29"]

VERTICAL_TO_NACE = {
    "Manufacturing": "C",
    "Automotive": "C29",
}
```

Consequently, every other vertical received a vertical-mapping gap even though
the downloaded Eurostat SBS file contains many additional NACE sectors.

## Changes made in analysis2

### 1. Configurable crosswalk

Added:

```text
analysis2/market_vertical_config.json
analysis2/market_verticals.py
```

The JSON file defines the NACE code, statistical scope, mapping quality and
limitation for every radar vertical. The Python helper validates the file and
provides one common crosswalk to the preparation and calculation scripts.

### 2. Expanded Eurostat preparation

Modified `07a_prepare_eurostat_sbs.py` so it reads all NACE codes required by
the crosswalk instead of only `C` and `C29`.

It now prepares 16 NACE denominator codes and writes:

```text
analysis2/reference/eurostat/vertical_nace_crosswalk.csv
```

### 3. Corrected adoption-proxy wording

Modified `07b_prepare_eurostat_ict_adoption.py`. Adoption rates are now labelled
as cross-vertical, non-financial-business proxies rather than Manufacturing
proxies.

### 4. Review rows for every opportunity

Modified `07c_prepare_comparable_contract_values.py`. The previous annual-value
template had zero rows because no opportunity had five eligible awards. The new
version writes all 205 scored opportunity spaces to the review template while
leaving all amounts blank.

This makes the evidence gap reviewable without fabricating financial values.

### 5. Multi-code vertical calculations

Modified `07d_calculate_market_potential.py` to:

- load the crosswalk from configuration;
- support one or several NACE components per vertical;
- aggregate composite verticals without losing their component metadata;
- add mapping quality and limitations to the output;
- calculate NACE-component coverage;
- distinguish missing vertical, technology and market-input problems; and
- map warehouse automation to the available IoT adoption proxy.

### 6. More transparent UX export

Modified `07f_build_opportunity_market_size_export.py` to export:

- NACE codes;
- vertical mapping status and quality;
- statistical scope and limitation;
- technology proxy and mapping status;
- country and NACE-component coverage; and
- explicit blocking reasons.

## Current vertical crosswalk

| Radar vertical | NACE scope | Quality |
|---|---|---|
| Aerospace | C303 | Narrow proxy |
| Automotive | C29 | Direct sector proxy |
| Defense | C254 | Narrow manufacturing proxy |
| Energy | D35 | Sector proxy |
| Finance, Banking, Insurance | K | Broad sector proxy |
| Healthcare | Q86 | Sector proxy |
| Lifesciences | C21 | Narrow pharmaceutical proxy |
| Manufacturing | C | Broad direct sector |
| Media & Entertainment | J58 + J59 + J60 | Composite proxy |
| Natural Resources | B | Mining/quarrying proxy |
| Public/Gov sector | Unsupported | SBS excludes the required public-administration denominator |
| Retail | G47 | Direct sector proxy |
| Transportation & Construction | F + H | Composite proxy |
| Wholesale | G46 | Direct sector proxy |

Totals from different radar verticals must not be added together. Manufacturing
contains Automotive, Aerospace, pharmaceuticals and defense manufacturing, so
cross-vertical addition would double-count enterprises.

## Results after rerunning analysis2

```text
Eurostat enterprise rows prepared: 860
Configured radar verticals: 14
Enabled NACE denominator codes: 16
Scored opportunities represented: 205
Mapped vertical + technology opportunities: 178
Technology-proxy gaps: 10
Public/Government denominator gaps: 17
```

Thirteen of fourteen verticals now have an SBS mapping. Public/Government still
requires a different public-sector denominator rather than an invented NACE
business proxy.

## Why all EUR values still show pending

The mapping expansion fixes the customer-denominator coverage, but market
potential also requires approved annual engagement values:

```text
Market potential = addressable enterprises × approved annual engagement value
```

The new assumption template contains:

```text
205 opportunity rows
192 with no taxonomy-linked awarded comparable
13 with fewer than five awarded observations
0 approved annual-value ranges
```

Therefore, all 205 UX records correctly remain `pending_or_unavailable`. The
program now has broader enterprise coverage, but it deliberately does not
invent EUR values.

## Next evidence tasks

1. Validate opportunity-level annual engagement values; the separate
   Public/Government denominator is now implemented from observed TED buyers.
2. Decide whether blockchain and 5G connectivity may use a defensible public
   adoption proxy; otherwise keep them blocked.
3. Validate annual low/central/high engagement values for selected opportunity
   spaces using public comparables.
4. Approve those rows in
   `analysis2/reference/market_sizing/annual_engagement_value_assumptions_template.csv`.
5. Rerun `07d` and `07f`.
6. Refresh the two files in the final Beta app's `imports/market_size/` folder
   after rerunning `07f`; the runtime join is now implemented with the stable
   `vertical|use_case_id|technology_id` key.

## Public/Government denominator added

`07a2_prepare_public_sector.py` prepares a separate public-sector evidence
path. It does not use NACE O employment or government expenditure as a market
value.

```text
Public opportunity denominator = distinct recent TED buyers linked to
                                 vertical x use case x technology

Public annual addressable potential = observed linked buyers
                                    x approved annual engagement value
```

Eurostat `nama_10_a64_e` contributes NACE O public-administration employment,
and `gov_10a_exp` contributes COFOG GF01/GF02 expenditure. Both are displayed
only as contextual indicators. The buyer denominator is a conservative observed
lower bound because procurement feeds do not represent every potential buyer.

Current preparation result:

- 29 configured European countries;
- 27 have NACE O employment context;
- 27 have GF01/GF02 expenditure context;
- 4,207 recent deduplicated TED buyers observed overall;
- 3 of the 17 scored Public/Government opportunity keys have opportunity-linked
  buyer evidence in the final 205-key export;
- all public EUR values remain pending until an annual engagement value is
  supported and approved.

## Safety rule

Use `analysis2/` for the experimental version. Keep `Analysis/` unchanged until
the crosswalk, assumptions and UX output have been reviewed.
