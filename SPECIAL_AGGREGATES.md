# UK CPI ex-CPI / special aggregates mapping

Status: the first exclusion set is mapped and has a validation-only MM23 reader. MM23 annual weights are intentionally **not persisted** yet.

## Why this stays in `collector_ons_cpi`

The ONS publishes the exclusion measures inside the same CPI statistical family. The current collector already ingests Table 38 analytical aggregates as `CPI_ALT_*` index-level series. MM23 adds the native relationship between each exclusion aggregate's annual weight, index and 12-month rate. Creating a separate repository would duplicate CPI index series and split one source family unnecessarily.

## Authoritative sources

- Table 38, Consumer price inflation detailed reference tables: stored monthly `ALT` index levels.
- MM23, Consumer price inflation time series: validation/mapping source for annual special-aggregate weights, related index CDIDs and published 12-month rates.
- W1-CPI: source for the standard COICOP basket hierarchy; MM23 does not replace it.
- ONS higher-level aggregation methodology: source for the CPI double-weight regime above consumption-segment level.

Current ONS methodology: above consumption-segment level CPI/CPIH use December-reference weights for January aggregation and January-reference weights for February through December. This is the reason a single annual MM23 weight must not be expanded to twelve monthly rows without first identifying which reference regime it represents.

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

The code representation is `scripts/special_aggregates.py`. Joins are exact on the native ONS CDID. Names are descriptive only and are never fuzzy mapping keys.

## What is implemented on this branch

### Exact Table 38 -> MM23 identity

`resolve_table38_alt_series()` maps each reviewed exclusion index CDID onto an already-collected Table 38 `ALT` series. It accepts only `family == ALT`, rejects duplicate native CDIDs and reports missing targets instead of fabricating a fallback.

The opt-in live-source replay now requires all ten reviewed index CDIDs to resolve against the current Table 38 source.

### MM23 parser

`parse_mm23_special_aggregates()` reads the official wide MM23 CSV and keeps only the 60 reviewed native series required by this layer:

- 10 exclusion weights, 10 exclusion indices and 10 exclusion 12-month rates;
- 10 removed-component weights, 10 removed-component indices and 10 removed-component 12-month rates.

The parser follows the published MM23 file contract: skip the title row, use the following `CDID` header, interpret `YYYY` rows as annual observations and `YYYY MON` rows as monthly observations, and ignore quarterly/unrelated rows. A missing reviewed CDID fails loudly.

`collect_mm23_special_aggregates()` downloads the current MM23 file through the collector's existing ONS HTTP allowlist, retry and download-size policy. It is currently called only by the opt-in live-source test, not by `main.py`.

### Complement-weight validation

For each exclusion, MM23 also publishes the weight of the removed component. `complement_weight_checks()` compares the two source-published weights directly against 1,000 parts per 1,000.

Example for 2026 core CPI:

```text
A9FU = 794.8781
A9G4 = 205.1219
sum  = 1000.0000
```

The live-source test checks the latest common annual observation for all ten pairs. This is stronger than reconstructing membership from series names.

## 12-month rate validation to add next

For a monthly Table 38 exclusion index `I`, calculate:

```text
100 * (I[t] / I[t-12] - 1)
```

and compare it with the related MM23 published rate CDID (`DKO8` for core, for example). MM23 rates are a validation source, not a second stored copy unless the modelling requirement explicitly asks for rate series.

## Unresolved storage question: annual MM23 weights

The MM23 exclusion weights are annual observations. The existing `original_weights` table is reference-month based and already preserves the two W1 regimes plus the separate consumption-segment basket boundary.

ONS currently documents two higher-level CPI weight reference periods each year:

- December-reference weights used for January;
- January-reference weights used for February through December.

The single annual MM23 special-aggregate value has not yet been proven to represent one specific regime, both regimes, or a publication summary with different semantics. Therefore this branch deliberately does not copy it into monthly `original_weights` rows.

Until that relationship is source-verified:

- Table 38 remains the stored monthly index source;
- MM23 remains mapping/validation input only;
- no monthly special-aggregate weights are fabricated;
- no `DK*` series already present as Table 38 `ALT` are duplicated;
- no database schema or standardized metadata contract changes.

## Remaining implementation tasks

1. Add Table 38 index -> MM23 published 12-month-rate validation and measure residuals on the live source.
2. Investigate the annual special-aggregate weight's exact relationship to the ONS December/January double-weight regimes.
3. Decide, based on that evidence, whether MM23 annual weights belong in `original_weights` or should remain validation-only.
4. Only if persistence is justified, integrate the MM23 layer into `main.py`, logging and audit export with the same fail-before-write discipline as the existing bottom-up checks.

## Revision evidence

MM23 exposes previous dataset versions. ONS also published a correction on 18 February 2026 for special-aggregate CDIDs `KYHJ`, `KYHK`, `KYHL`, `KYHM` and `KYHQ` after double-linked indices had been used instead of single-linked indices for January 2026. Those rental aggregates are not part of the ten exclusion measures above, but the correction is direct evidence that special-aggregate validation and vintage awareness are necessary.
