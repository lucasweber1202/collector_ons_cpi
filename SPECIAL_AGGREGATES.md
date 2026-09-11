# UK CPI ex-CPI / special aggregates mapping

Status: the first exclusion set is mapped and has validation-only MM23 weight and 12-month-rate checks. The weight-regime semantics are now source-verified; persistence is still held back until the historical January regimes are collected from MM23 snapshots and the full verification loop passes.

## Why this stays in `collector_ons_cpi`

The ONS publishes the exclusion measures inside the same CPI statistical family. The current collector already ingests Table 38 analytical aggregates as `CPI_ALT_*` index-level series. MM23 adds the native relationship between each exclusion aggregate's annual weight, index and 12-month rate. Creating a separate repository would duplicate CPI index series and split one source family unnecessarily.

## Authoritative sources

- Table 38, Consumer price inflation detailed reference tables: stored monthly `ALT` index levels.
- MM23, Consumer price inflation time series: validation/mapping source for special-aggregate weights, related index CDIDs and published 12-month rates.
- W1-CPI: source for the standard COICOP basket hierarchy; MM23 does not replace it.
- ONS higher-level aggregation methodology and annual weights release: source for the CPI double-weight regime above consumption-segment level.

ONS uses two higher-level CPI/CPIH weight updates from 2017 onward: December-reference weights for January aggregation and January-reference weights for February through December.

## Reviewed exclusion crosswalk

| Exclusion measure | MM23 weight | Monthly index | Published 12m rate | Removed component weight | Removed component index | Removed component 12m rate |
| --- | --- | --- | --- | --- | --- | --- |
| CPI excluding tobacco | `A9F5` | `DK9V` | `DKL7` | `CJWP` | `D7CB` | `D7GN` |
| CPI excluding energy | `A9FT` | `DKC5` | `DKO7` | `A9F3` | `DK9T` | `DKL5` |
| CPI excluding energy, food, alcohol and tobacco (core) | `A9FU` | `DKC6` | `DKO8` | `A9G4` | `DKD6` | `DKP8` |
| CPI excluding energy and unprocessed food | `A9FV` | `DKC7` | `DKO9` | `A9G5` | `DKD7` | `DKP9` |
| CPI excluding seasonal food | `A9FW` | `DKC8` | `DKP2` | `A9EZ` | `DK9R` | `DKL3` |
| CPI excluding energy and seasonal food | `A9FX` | `DKC9` | `DKP3` | `A9G6` | `DKD8` | `DKQ2` |
| CPI excluding alcohol and tobacco | `A9FY` | `DKD2` | `DKP4` | `CHZS` | `D7BV` | `D7G9` |
| CPI excluding liquid fuels, vehicle fuels and lubricants | `A9FZ` | `DKD3` | `DKP5` | `A9FS` | `DKC4` | `DKO6` |
| CPI excluding housing, water, electricity, gas and other fuels | `A9G2` | `DKD4` | `DKP6` | `CHZU` | `D7BX` | `D7GB` |
| CPI excluding education, health and social protection | `A9G3` | `DKD5` | `DKP7` | `A9G7` | `DKD9` | `DKQ3` |

The identity map and MM23 parser live in `scripts/special_aggregates.py`. Joins are exact on the native ONS CDID. Names are descriptive only and are never fuzzy mapping keys. Cross-source Table 38 -> MM23 rate reconciliation lives in `scripts/special_aggregate_rates.py`.

## What is implemented on this branch

### Exact Table 38 -> MM23 identity

`resolve_table38_alt_series()` maps each reviewed exclusion index CDID onto an already-collected Table 38 `ALT` series. It accepts only `family == ALT`, rejects duplicate native CDIDs and reports missing targets instead of fabricating a fallback.

The opt-in live-source replay requires all ten reviewed index CDIDs to resolve against the current Table 38 source.

### MM23 parser

`parse_mm23_special_aggregates()` reads the official wide MM23 CSV and keeps only the 60 reviewed native series required by this layer:

- 10 exclusion weights, 10 exclusion indices and 10 exclusion 12-month rates;
- 10 removed-component weights, 10 removed-component indices and 10 removed-component 12-month rates.

The parser follows the published MM23 file contract: skip the title row, use the following `CDID` header, interpret `YYYY` rows as annual observations and `YYYY MON` rows as monthly observations, and ignore quarterly/unrelated rows. A missing reviewed CDID fails loudly.

`collect_mm23_special_aggregates()` downloads the current MM23 file through the collector's existing ONS HTTP allowlist, retry and download-size policy. It is currently called only by the opt-in live-source test, not by `main.py`.

### Complement-weight validation

For each exclusion, MM23 also publishes the weight of the removed component. `complement_weight_checks()` compares the two source-published weights directly against 1,000 parts per 1,000.

Example for the current 2026 core CPI regime:

```text
A9FU = 794.8781
A9G4 = 205.1219
sum  = 1000.0000
```

The live-source test checks the latest common annual observation for all ten pairs. This is stronger than reconstructing membership from series names.

### Published 12-month-rate validation

`published_12m_rate_checks()` takes the already-collected Table 38 `ALT` levels and calculates, for every reviewed exclusion aggregate:

```text
100 * (I[t] / I[t-12] - 1)
```

It then compares that value with the related MM23 published 12-month-rate CDID (`DKO8` for core, for example). The default tolerance is 0.10 percentage point to accommodate the published rate rounding while Table 38 carries analytical levels to three decimals.

The unit tests cover all ten aggregates, a deliberately wrong MM23 rate, a missing Table 38 target and latest-month selection. The opt-in live-source replay checks the latest common month for all ten aggregates. MM23 rates remain validation-only and are not stored as duplicate time series.

## Weight-regime semantics: resolved

The current MM23 annual weight is not a generic twelve-month weight. Official 2026 releases show that it is the **second CPI weight update used from February through December**.

For core CPI:

```text
January 2026 bulletin:  CPI excluding energy, food, alcohol and tobacco = 796.0030
Current MM23 A9FU:                                                = 794.8781
```

For the energy component:

```text
January 2026 bulletin:  energy = 58.3320
Current MM23 A9F3:             = 58.3510
```

The current MM23 values match the weights used in the February-December 2026 CPI tables. This is consistent with ONS's documented double-update method: the first update is used only for January; the second update is introduced with the February index released in March.

### How to recover January without inventing a value

MM23 preserves superseded dataset versions. The full dataset history shows a version superseded on 25 March 2026 at 07:00, immediately before the second 2026 weight update became current. Its CSV is stored under the versioned MM23 path `previous/v130/mm23.csv`. That snapshot represents the January-weight regime after the February CPI release. The later/current MM23 snapshot represents the February-December regime.

Therefore the source-backed storage design is:

```text
pre-2017: one published annual regime -> January through December
2017 onward:
    February-release MM23 snapshot -> January reference month only
    March-release/current MM23 snapshot -> February through December
```

A historical build must combine the two source vintages for each double-update year. It must not fill January with the later Feb-Dec value when the February snapshot is unavailable.

## What is still deliberately not persisted

The evidence now supports the regime interpretation, but this branch still does not write MM23 special-aggregate weights to `original_weights`. Before changing persistence, the collector needs a reviewed historical snapshot discovery/selection step and a live replay proving that both annual regimes are recovered without gaps or collisions.

Until that gate exists:

- Table 38 remains the stored monthly index source;
- MM23 remains mapping/validation input only;
- no monthly special-aggregate weights are fabricated;
- no `DK*` series already present as Table 38 `ALT` are duplicated;
- no database schema or standardized metadata contract changes.

## Remaining implementation tasks

1. Implement MM23 historical snapshot discovery and select the February and March weight snapshots for each double-update year.
2. Build the two source-backed monthly weight regimes and test that January and February-December are never silently conflated.
3. Run the full local verification loop and opt-in live replay, recording measured rate and weight residuals.
4. If all gates pass, persist the reviewed ex-CPI weights in `original_weights` and integrate the checks into `main.py` before writes.
5. Extend the audit workbook and `COMPLIANCE.md` with the new source/vintage semantics.

## Revision evidence

MM23 exposes previous dataset versions. ONS also published a correction on 18 February 2026 for special-aggregate CDIDs `KYHJ`, `KYHK`, `KYHL`, `KYHM` and `KYHQ` after double-linked indices had been used instead of single-linked indices for January 2026. Those rental aggregates are not part of the ten exclusion measures above, but the correction is direct evidence that special-aggregate validation and vintage awareness are necessary.
