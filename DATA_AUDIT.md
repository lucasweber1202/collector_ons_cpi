# Data audit — collector_ons_cpi

- Audit seed: `20260918`
- Source version: live capture on 2026-09-18
- Test result: **340 passed, 3 skipped**
- Execution: **PASS**
- Overall: **PARTIAL** — Target oficial; Table 38 atual validada. Vintages preservam coletas futuras, mas o arquivo atual não reconstrói edições históricas.
- Output: 73,459 observations, 163 series, 1988-01-01 to 2026-08-01.
- Sample: 20; values matched: 20; failures: 0; not verifiable: 0.

## Observation evidence

| # | Series | Period | Collector | Official source | Unit/frequency evidence | Result |
|---:|---|---|---:|---:|---|---|
| 1 | `CPI_COICOP_C0732_D7EG` | 1988-01-01 | 29.43 | 29.43 | index 2015=100; monthly; Table 38!BX8 | **PASS** |
| 2 | `CPI_ALT_A59_DK9S` | 2026-08-01 | 131.271 | 131.271 | index 2015=100; monthly; Table 38!FS471 | **PASS** |
| 3 | `CPI_COICOP_C0912_D7EO` | 1988-12-01 | 2247.692 | 2247.692 | index 2015=100; monthly; Table 38!CG19 | **PASS** |
| 4 | `CPI_COICOP_C0454_D7DW` | 1996-02-01 | 39.982 | 39.982 | index 2015=100; monthly; Table 38!AP105 | **PASS** |
| 5 | `CPI_COICOP_G094_D7CV` | 1994-08-01 | 49.589 | 49.589 | index 2015=100; monthly; Table 38!CR87 | **PASS** |
| 6 | `CPI_COICOP_G123_D7FO` | 1994-02-01 | 76.001 | 76.001 | index 2015=100; monthly; Table 38!DJ81 | **PASS** |
| 7 | `CPI_ALT_A17_DKA3` | 2012-09-01 | 100.45 | 100.45 | index 2015=100; monthly; Table 38!EI304 | **PASS** |
| 8 | `CPI_ALT_A13_DK9T` | 2004-04-01 | 52.028 | 52.028 | index 2015=100; monthly; Table 38!EE203 | **PASS** |
| 9 | `CPI_COICOP_C0911_D7EN` | 2007-08-01 | 188.529 | 188.529 | index 2015=100; monthly; Table 38!CF243 | **PASS** |
| 10 | `CPI_COICOP_G124_D7D2` | 2013-12-01 | 94.735 | 94.735 | index 2015=100; monthly; Table 38!DM319 | **PASS** |
| 11 | `CPI_COICOP_C0441_D7DR` | 2025-11-01 | 165.513 | 165.513 | index 2015=100; monthly; Table 38!AJ462 | **PASS** |
| 12 | `CPI_COICOP_G073_D7CQ` | 2026-04-01 | 154.343 | 154.343 | index 2015=100; monthly; Table 38!BV467 | **PASS** |
| 13 | `CPI_COICOP_C0454_D7DW` | 2026-05-01 | 154.906 | 154.906 | index 2015=100; monthly; Table 38!AP468 | **PASS** |
| 14 | `CPI_COICOP_C1112_D7EX` | 2026-02-01 | 115.644 | 115.644 | index 2015=100; monthly; Table 38!DD465 | **PASS** |
| 15 | `CPI_COICOP_C0122_D7DF` | 1990-04-01 | 53.292 | 53.292 | index 2015=100; monthly; Table 38!Q35 | **PASS** |
| 16 | `CPI_COICOP_C0711_D7E8` | 2015-04-01 | 100.064 | 100.064 | index 2015=100; monthly; Table 38!BO335 | **PASS** |
| 17 | `CPI_COICOP_C0951_D7FK` | 1999-05-01 | 70.402 | 70.402 | index 2015=100; monthly; Table 38!CV144 | **PASS** |
| 18 | `CPI_COICOP_G051_D7CI` | 2001-08-01 | 79.864 | 79.864 | index 2015=100; monthly; Table 38!AR171 | **PASS** |
| 19 | `CPI_ALT_A51_DK9K` | 2001-11-01 | 115.904 | 115.904 | index 2015=100; monthly; Table 38!FK174 | **PASS** |
| 20 | `CPI_ALT_A10_DK9X` | 2000-05-01 | 83.013 | 83.013 | index 2015=100; monthly; Table 38!EB156 | **PASS** |

## Filtering and metadata

- `{"universe_native_columns":173,"selected":163}`

The audit read the captured official artifact independently of the collector parser. It checked identifier linkage, published labels, units, frequency and first/latest boundaries. Source artifacts are identified by SHA-256 in the audit evidence.

## Point-in-time and revisions

Predictor as-of queries filter availability before ranking vintages. `inferred` and `unknown` remain excluded by default. Current mutable-file backfills are recorded at `first_seen`; later observed revisions create later vintages and do not inherit an original release timestamp. Actual pre-collection historical editions remain `NOT_VERIFIABLE` unless an archived source file exists.

## Corrections

- No source-semantic bug was found in this repository during the sample.

## Result

**PARTIAL** — Target oficial; Table 38 atual validada. Vintages preservam coletas futuras, mas o arquivo atual não reconstrói edições históricas.
