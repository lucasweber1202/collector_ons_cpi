# UK CPI ex-CPI / special aggregates mapping

Status: mapping phase complete for the first exclusion set; persistence of MM23 annual weights is intentionally not implemented yet.

## Why this stays in `collector_ons_cpi`

The ONS publishes the exclusion measures inside the same CPI statistical family. The current collector already ingests Table 38 analytical aggregates as `CPI_ALT_*` index-level series. MM23 adds the native relationship between each exclusion aggregate's annual weight, index and 12-month rate. Creating a separate repository would duplicate CPI index series and split one source family unnecessarily.

## Authoritative sources

- Table 38, Consumer price inflation detailed reference tables: current source of the monthly `ALT` index levels collected by this repository.
- MM23, Consumer price inflation time series: source of annual special-aggregate weights, related index CDIDs and published 12-month rates.
- W1-CPI remains the source for the standard COICOP basket hierarchy and is not replaced by MM23.

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

The code representation of this table is `scripts/special_aggregates.py`. All joins must be exact on the ONS native CDID. Names are descriptive only and must never be used as a fuzzy mapping key.

## Strong source-level checks now available

### 1. Table 38 -> MM23 identity

For each exclusion index CDID, resolve the existing Table 38 `ALT` series by `native_id`. A missing or duplicate ALT match is a source-scope change and must be surfaced explicitly.

### 2. 12-month rate check

For a monthly index `I`, compare the rate calculated from the collected index with the MM23 published rate:

```text
100 * (I[t] / I[t-12] - 1)
```

The published MM23 rate is a validation source, not a second stored copy of the same information unless the modelling requirement later explicitly asks for rate series.

### 3. Complement weight check

MM23 publishes the excluded aggregate weight and an official removed-component weight. For the same annual observation the pair should reconcile to 1,000 parts per 1,000.

Example for 2026 core CPI:

```text
A9FU = 794.8781
A9G4 = 205.1219
sum  = 1000.0000
```

This is preferable to reconstructing the exclusion composition from names.

## Important unresolved storage question

MM23 publishes these weights as annual observations. The collector's current `original_weights` table is explicitly reference-month based and already distinguishes January from February-December W1 regimes and the February-to-January consumption-segment basket.

Therefore the annual MM23 weight must **not** simply be copied into all twelve months until the ONS semantics are tied to the collector's regime logic. Doing so could imply a monthly weight regime that the source did not publish.

Until that is resolved:

- keep Table 38 as the stored monthly index source;
- keep MM23 weights as validation/mapping inputs only;
- do not fabricate monthly `original_weights` rows from one annual value;
- do not duplicate `DK*` index series already present as Table 38 `ALT` series.

## Next implementation tasks

1. Live-source gate: verify that all ten reviewed index CDIDs resolve to Table 38 `ALT` rows on the current workbook.
2. MM23 reader: collect only the reviewed native IDs needed for validation, preserving release/vintage identity.
3. Rate validation: compare calculated 12-month changes from Table 38 with MM23 published rates.
4. Complement validation: verify annual exclusion + removed-component weights equal 1,000 within a tight source-rounding tolerance.
5. Determine MM23 annual-weight regime semantics relative to W1 January and February-December regimes before any persistence change.
6. Only after task 5, decide whether MM23 annual weights belong in `original_weights` or should remain a validation-only source.
