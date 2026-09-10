# UK CPI guideline compliance — approved implementation

Baseline: the user-supplied initial MASTER_MACRO_COLLECTOR_GUIDELINES.md,
SHA-256 `59739074fd125161929dda70828d7876de548ceef110dddfa7c12ec38fc9c72e`.
The governance copy is restored byte-for-byte. Exceptions below are UK-local;
they do not redefine the fleet contract. Status: **building; not production-certified**.

## Approved exceptions and exact storage semantics

- Standard metadata, time_series and logs schemas remain unchanged.
- PostgreSQL emits DOUBLE PRECISION; Databricks emits DOUBLE (both 64-bit).
- original_weights retains weight_base_year and collected_at, adding
  reference_date and vintage_date with key (series_id, reference_date, vintage_date).
  This is the user-approved regime-safe exception: a series-only key cannot preserve
  January versus February–December or revisions.
- original_weights stores W1 values in source points per thousand without normalization.
  weight_base_year denotes the W1 application year, not an inferred expenditure-survey year.
  Source identifiers encode W1 codes: CPI_W1_01P1P1P1 means 01.1.1.1;
  P encodes a dot and S encodes a slash. A/B suffixes remain distinct.
  ALLGOODS/ALLSERVICES and 0 denote the source analytical totals and overall index.
- weights stores local operational shares for each immediate parent. The root and
  standalone analytical aggregates receive 1.0. These shares multiply monthly
  index relatives directly; consumers must not price-update them a second time.
- The correct price-reference denominator in METHODOLOGY.md is retained as the
  approved UK formula exception. It is required for Table 38's 2015=100 levels.

## Source scope and evidence (2026-09-10)

Current Table 38: 173 series, comprising 122 COICOP nodes and 51 overlapping
analytical aggregates. First published observations vary by series; the full
table spans January 1988–July 2026. The publication stamp is 19 August 2026.
Table 38 supplies **three-decimal** index levels, not one-decimal levels.

Current W1: 319 classified/total rows preserved, including 192 subclass rows,
rather than dropping everything below COICOP class. These expand into 228 months
from January 2008 to December 2026; future regime months are published weights,
not fabricated future observations. Only 122 Table 38 series have mapped W1
COICOP basket weights. Weight-only rows do not get invented index observations
or misleading metadata rows.

Live source reconciliation completed:

| Check | Performed | Failed | Coverage | Maximum absolute residual |
| --- | ---: | ---: | ---: | ---: |
| W1 immediate-child sums | 8,436 | 0 | 100% | 0.0002 points per thousand |
| Official-basket price-reference formula | 8,251 | 0 | 100% | 0.0019795967 percentage points |
| Derived operational shares | 8,251 | 0 | 100% | 0.0019795967 percentage points |

Only months before the actual W1 start (2008) are excluded from the coverage
denominator. Missing recent weights, missing observations/references and
nonconsecutive observation months count against coverage. Tolerance failures,
empty checks and coverage below the configured floor stop data persistence.
The legacy --strict-validation argument remains accepted but cannot disable gates.

Mappings use exact nodes or a reviewed W1-code-to-CDID alias dictionary in
scripts/extract.py. No fuzzy scoring remains. Ambiguous nodes, missing reviewed
CDIDs, conflicting values and unresolved hierarchy parents fail explicitly.
Agreeing duplicate mappings remain reported and source rows remain separate.
Original Weight Map in the export records every original code, label and target.

## Database upgrade safety

Existing versions stored official points per thousand in weights. The new
pipeline checks for that legacy representation **before any data write** and
refuses to mix it with local operational shares. It does not automatically
overwrite or delete historical vintages.

Deployment to an existing populated database requires a reviewed archival and
full-history rebuild plan using its actual data and backups. For verification,
use a separate empty database with the standard collector schema. Do not drop
the existing production weights table merely to pass this check. No existing
production database has been migrated by this change.

scripts/original_weights.py is a flat, collector-local persistence module. It
follows the existing batch/upsert pattern rather than introducing a shared
framework, ORM or migration system.

## Verification commands

```bash
python -m pytest -q -W ignore::DeprecationWarning
ruff check .
ruff format --check .
python -m compileall -q main.py scripts tests
ONS_LIVE_TEST=1 python -m pytest tests/test_live_source.py -q -W ignore::DeprecationWarning
```

Regression tests cover conflicts, ambiguous mapping, subclass retention,
operational shares, January chain inputs, missing-source coverage, mandatory
gates, same-day/later-day vintages, regime-safe original weights, legacy storage
protection, release polling, export sheets and logged failures.
The opt-in live test replays a downloaded ONS snapshot twice into an isolated
SQLite database, compares full persisted rows, checks three observations per
series and distinct counts, then injects a validation failure and checks that
only the execution log changes. This is not a PostgreSQL/Databricks certification
or an independent statistical replication of the ONS source itself.

Executed results: 49 local tests passed (live test skipped by default); the
explicit live test passed separately. The full replay persisted 77,926
observations, 38,579 operational weights, 56,436 original weights and 173
metadata rows. Two successful runs and one injected failure produced three logs
with statuses success, success, error. Ruff lint/format, compilation and the
installed-dependency compatibility check passed.

## Remaining release gates — do not mark ready

1. Execute real PostgreSQL and Databricks DDL/MERGE and full two-run/error tests
   in approved test environments. Neither a local PostgreSQL server nor a
   configured Databricks test environment has been verified here.
2. Identify the live pilot requested by the master guideline and perform the
   exact compatibility review against it.
3. Review migration against actual pre-existing database vintages and backups.
4. Complete the broader consumption-segment demand. ONS publishes consumption
   segment CPI indices/weights and historical classification files in its
   item-indices dataset, but labels these research microdata as **not accredited
   official statistics**. Historical changes, annual index reference bases,
   classification changes and suppressed components require separate source
   treatment. This implementation does not stitch those levels into Table 38,
   fabricate subclass index levels from weights, or claim deepest-level
   reconstruction. The intake request remains open for this work.
5. Complete independent source/metadata sampling and deployment security review
   against the target runtime; passing parser-to-database replay alone does not
   satisfy every Phase 8 item.

Sources:
- [ONS CPI detailed tables](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceinflation)
- [ONS W1–W3 weights](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceinflationupdatingweightsannexatablesw1tow3)
- [ONS higher-level aggregation](https://www.ons.gov.uk/economy/inflationandpriceindices/methodologies/higherlevelaggregationandweightsinconsumerprices)
- [ONS item/consumption-segment indices and classification files](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceindicescpiandretailpricesindexrpiitemindicesandpricequotes)
