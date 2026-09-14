# UK CPI guideline compliance — evidence of the current state

Baseline: `lucasweber1202/Coletores/MASTER_MACRO_COLLECTOR_GUIDELINES.md`,
SHA-256 `59739074fd125161929dda70828d7876de548ceef110dddfa7c12ec38fc9c72e`,
re-read from the live governance repository on 2026-09-14. Exceptions below are
UK-local; they do not redefine the fleet contract. Every status in this document
is `PASS`, `FAIL`, or `SKIP` with the reason stated.

## Scope: this repository is the UK CPI headline collector only

`collector_ons_cpi` collects the published UK CPI index levels, the official
basket weights and the consumption-segment layer. The CPI **exclusion special
aggregates** (the MM23 "CPI excluding ..." series) are a separate dataset and
live in their own repository, `lucasweber1202/collector_ons_ex_cpi`. Nothing in
this repository reads, imports or depends on it, and the fleet rule against a
shared core means neither repository may grow a common package for the other.

Verified on 2026-09-14 against `origin/main` at `0f80765`:

| Check | Result |
| --- | --- |
| MM23 special-aggregate pipeline in `main` | absent |
| EX-CPI persistence (table, column or write path) in `main` | absent |
| Special-aggregate weight registration in `main` | absent |
| Any dependency on `collector_ons_ex_cpi` | absent |
| `git log main -S MM23` | no commit ever introduced it |

The earlier branch `feature/ex-cpi-special-aggregates-mapping` and its pull
request [#7](https://github.com/lucasweber1202/collector_ons_cpi/pull/7) remain
as history. PR #7 is **closed and was never merged**, and the branch now points
at the same commit as `main`, so it carries no EX-CPI commits. It must not be
merged into `main`; EX-CPI development continues in its own repository.

---

## Approved exceptions and exact storage semantics

- Standard `metadata`, `time_series` and `logs` schemas remain unchanged.
- PostgreSQL emits `DOUBLE PRECISION`; Databricks emits `DOUBLE` (both 64-bit).
  `FLOAT` is never emitted: it is 8 bytes on PostgreSQL and 4 on Databricks.
- `original_weights` retains `weight_base_year` and `collected_at`, adding
  `reference_date` and `vintage_date` with key
  `(series_id, reference_date, vintage_date)`. This is the user-approved
  regime-safe exception: a series-only key cannot preserve January versus
  February–December, the February-to-January consumption-segment basket, or
  revisions.
- `original_weights` stores official values without normalization: W1 rows in
  source points per thousand and consumption-segment `CPI_WEIGHT` in parts per
  thousand. `weight_base_year` is the **published regime year**, supplied per
  row because the two products run different annual boundaries — W1 labels
  January and February–December of one calendar year, while a segment basket
  runs February to the following January.
- W1 source identifiers encode the workbook code: `CPI_W1_01P1P1P1` means
  `01.1.1.1`; `P` encodes a dot and `S` a slash. A/B suffixes stay distinct.
  `ALLGOODS`, `ALLSERVICES` and `0` denote the source analytical totals and the
  overall index. Consumption-segment weights use the segment's own series
  identifier, so `original_weights` joins directly to `metadata` for that layer.
- `weights` stores local operational shares for each immediate parent. The root
  and standalone analytical aggregates receive 1.0. These shares multiply
  monthly index relatives directly; consumers must not price-update them again.
- The price-reference denominator documented in METHODOLOGY.md is the approved
  UK formula exception; it is required for Table 38's 2015=100 levels.
- `scripts/segments.py` is one extra source-specific module. It is justified by
  the source, not by taste: consumption segments come from a different ONS
  dataset, carry a different statistical status, use a different index
  reference, and arrive in two published layouts, one of which needs the CPI
  classification framework file. Folding it into `extract.py` would put three
  unrelated parsing contracts in one module and push it past 1,000 lines. No
  shared core, base class, ORM, migration framework or cross-repo import is
  introduced.

## Source scope and evidence (replayed 2026-09-14, publication stamp 19 August 2026)

Stored on a real PostgreSQL 16.13 database from a full historical build:

| Layer | Series | Observations | First | Last |
| --- | ---: | ---: | --- | --- |
| COICOP (all items, 12 divisions, 38 groups, 71 classes) | 122 | 54,516 | 1988-01-01 | 2026-07-01 |
| ONS analytical aggregates | 51 | 23,410 | 1988-01-01 | 2026-07-01 |
| Consumption segments | 697 | 12,138 | 2025-02-01 | 2026-07-01 |
| **Total** | **870** | **90,064** | | |

Weights:

| Table | Rows | Distinct series | First | Last |
| --- | ---: | ---: | --- | --- |
| `original_weights`, W1 codes | 56,436 | 319 | 2008-01-01 | 2026-12-01 |
| `original_weights`, segment weights | 12,138 | 697 | 2025-02-01 | 2026-07-01 |
| `weights`, COICOP operational shares | 27,206 | 122 | 2008-01-01 | 2026-07-01 |
| `weights`, analytical roots at 1.0 | 11,373 | 51 | 2008-01-01 | 2026-07-01 |
| `weights`, segment operational shares | 10,115 | 697 | 2025-03-01 | 2026-07-01 |

Segment shares start in March and skip every January and February because the
January re-reference leaves those links undefined at source; no share is
invented for a month whose link does not exist.

Only 122 of the 173 Table 38 series have mapped W1 COICOP basket weights; the
51 analytical aggregates are overlapping cuts with no basket row. 192 W1
subclass rows and the merged/total rows have official weights and no published
index: their weights are preserved and no index, metadata row or operational
weight is fabricated for them. 697 consumption segments resolve onto 85 distinct
published Table 38 parents.

### Reconciliation contract

Six layers are reconciled on every run; the executed figures are under
"Bottom-up reconciliation on the current source" below.

8,843 COICOP links fall before the 2008 weights window and 170 segment links
cross the January re-reference. Both are unreconcilable at source, are reported
separately, and are excluded from the coverage denominator. Every other skip
counts against coverage. Tolerance failures, an empty reconcilable layer and
coverage below the configured floor stop data persistence. The legacy
`--strict-validation` argument is still accepted and cannot disable any gate.

### Mapping discipline

Mappings use official classification codes, then the reviewed W1-code-to-CDID
alias dictionary in `scripts/extract.py`, then the two-entry subclass alias in
`scripts/segments.py` that separates new from second-hand cars inside class
07.1.1. No fuzzy scoring exists anywhere. Ambiguous nodes, missing reviewed
CDIDs, conflicting values, unresolved hierarchy parents, unclassifiable segments
and conflicting classification-framework rows all raise. Agreeing duplicate
mappings are reported and the source rows stay separate. The audit workbook's
Original Weight Map records every official code, CDID, label and target.

## Identifier migration — required before deploying to an existing database

`series_id` no longer embeds the official series name. The previous spelling was
`CPI_COICOP_D01_D7BU_FOOD_AND_NON_ALCOHOLIC_BEVERAGES`; the current spelling is
`CPI_COICOP_D01_D7BU`. The change removes a real defect: an ONS title edit
previously forked a series' stored history into two identifiers.

`assert_current_series_ids` runs inside the write transaction, before any data
is written, and refuses to proceed when `metadata` or `time_series` still holds
the old spelling. Nothing is renamed, deleted or rewritten automatically, so a
database that has not been migrated fails loudly and writes nothing.

The current identifier is the first four underscore-separated parts of the old
one, so the migration is a rename in place. It touches only rows carrying more
than the three underscores of `CPI_{family}_{node}_{native_id}`: the
`CPI_W1_*` rows in `original_weights` have two and are never rewritten.

### Step 0 — back up, on the database itself

Take a restorable copy before the transaction, not a logical export of the rows
you are about to change:

```bash
pg_dump --format=custom --schema=collector_ons_cpi \
        --file=collector_ons_cpi_pre_id_migration.dump "$COLLECTOR_DB_URL"
pg_restore --list collector_ons_cpi_pre_id_migration.dump | head   # prove it is readable
```

Record the row counts you expect to be unchanged afterwards:

```sql
SELECT (SELECT count(*) FROM collector_ons_cpi.time_series)      AS time_series,
       (SELECT count(*) FROM collector_ons_cpi.weights)          AS weights,
       (SELECT count(*) FROM collector_ons_cpi.original_weights) AS original_weights,
       (SELECT count(*) FROM collector_ons_cpi.metadata)         AS metadata,
       (SELECT count(DISTINCT vintage_date) FROM collector_ons_cpi.time_series) AS vintages,
       (SELECT round(sum(value)::numeric, 3) FROM collector_ons_cpi.time_series) AS checksum;
```

### Step 1 — dry run: what would be renamed

```sql
SELECT series_id AS old_series_id,
       split_part(series_id, '_', 1) || '_' || split_part(series_id, '_', 2) || '_' ||
       split_part(series_id, '_', 3) || '_' || split_part(series_id, '_', 4) AS new_series_id
FROM collector_ons_cpi.metadata
WHERE series_id LIKE 'CPI%'
  AND LENGTH(series_id) - LENGTH(REPLACE(series_id, '_', '')) > 3
ORDER BY series_id;
```

### Step 2 — collision pre-check: must return zero rows

Two distinct old identifiers collapsing onto one new one, or an old identifier
colliding with a row that is already migrated, would merge two histories under a
single key. Both cases are detected here, before anything is written:

```sql
WITH renamed AS (
    SELECT series_id AS old_series_id,
           split_part(series_id, '_', 1) || '_' || split_part(series_id, '_', 2) || '_' ||
           split_part(series_id, '_', 3) || '_' || split_part(series_id, '_', 4) AS new_series_id
    FROM collector_ons_cpi.metadata
    WHERE series_id LIKE 'CPI%'
      AND LENGTH(series_id) - LENGTH(REPLACE(series_id, '_', '')) > 3
)
SELECT new_series_id, count(*) AS colliding_old_ids, string_agg(old_series_id, ' | ') AS detail
FROM renamed GROUP BY new_series_id HAVING count(*) > 1
UNION ALL
SELECT r.new_series_id, 0, 'collides with an already-migrated row'
FROM renamed r
JOIN collector_ons_cpi.metadata m ON m.series_id = r.new_series_id;
```

**If this returns any row, stop.** Two old identifiers can only collapse when ONS
published two rows with the same family, node and CDID, which `parse_cpi_workbook`
rejects at extraction; a hit here means the stored data predates that gate and
needs a decision per series, not a bulk rename.

### Step 3 — apply, in one transaction

The map is materialised first so that renaming `metadata` last cannot change the
set of rows the other three tables are matched against:

```sql
BEGIN;
CREATE TEMP TABLE series_id_migration ON COMMIT DROP AS
SELECT series_id AS old_series_id,
       split_part(series_id, '_', 1) || '_' || split_part(series_id, '_', 2) || '_' ||
       split_part(series_id, '_', 3) || '_' || split_part(series_id, '_', 4) AS new_series_id
FROM collector_ons_cpi.metadata
WHERE series_id LIKE 'CPI%'
  AND LENGTH(series_id) - LENGTH(REPLACE(series_id, '_', '')) > 3;

UPDATE collector_ons_cpi.time_series t      SET series_id = m.new_series_id
  FROM series_id_migration m WHERE t.series_id = m.old_series_id;
UPDATE collector_ons_cpi.weights w          SET series_id = m.new_series_id
  FROM series_id_migration m WHERE w.series_id = m.old_series_id;
UPDATE collector_ons_cpi.original_weights o SET series_id = m.new_series_id
  FROM series_id_migration m WHERE o.series_id = m.old_series_id;
UPDATE collector_ons_cpi.metadata d         SET series_id = m.new_series_id
  FROM series_id_migration m WHERE d.series_id = m.old_series_id;
COMMIT;
```

PostgreSQL runs this as one transaction: either every table is renamed or none
is. Do not split it across sessions.

### Step 4 — verify before collecting

```sql
SELECT 'legacy rows left', count(*) FROM collector_ons_cpi.metadata
  WHERE series_id LIKE 'CPI%' AND LENGTH(series_id)-LENGTH(REPLACE(series_id,'_','')) > 3
UNION ALL SELECT 'orphan observations', count(DISTINCT t.series_id)
  FROM collector_ons_cpi.time_series t
  LEFT JOIN collector_ons_cpi.metadata m USING (series_id) WHERE m.series_id IS NULL
UNION ALL SELECT 'W1 rows preserved', count(*) FROM collector_ons_cpi.original_weights
  WHERE series_id LIKE 'CPI_W1_%';
```

The first two must be `0`; the third must equal its pre-migration value. Re-run
the Step 0 counts: every one of them, the vintage count and the checksum
included, must be unchanged. Then run `python main.py --no-watch`; it must exit
`0` and report zero writes on every table.

### Rehearsal executed 2026-09-14

This procedure was executed end to end against a **real populated PostgreSQL
16.13 database** — a copy of the full live-source build described above, 870
series and 90,065 observations across two vintages — after rewriting every
identifier into the superseded name-bearing spelling:

| Step | Result |
| --- | --- |
| Detector before migration | refused the run, wrote one `error` log, wrote 0 rows |
| Step 2 collision pre-check | 0 rows |
| Step 3 apply | 870 mapped; 90,065 / 48,694 / 12,138 / 870 rows renamed |
| `CPI_W1_*` rows in `original_weights` | 56,436 before and after, untouched |
| Row counts, distinct series, distinct vintages | unchanged |
| `sum(value)` checksum | `9499174.834` before and after |
| Both vintages of a revised observation | both preserved, neither rewritten |
| Legacy rows left / orphan observations | 0 / 0 |
| `python main.py --no-watch` afterwards | exit `0`, zero writes on all four tables |

**No production database has been migrated.** The rehearsal proves the procedure
on real data of the real shape; running it against production remains an
operator action, and gate 3 below stays open for that reason.

## Database upgrade safety

Earlier versions stored official points per thousand in `weights`. The pipeline
checks for that legacy representation **inside the write transaction, before any
data write**, and refuses to mix it with local operational shares. It does not
overwrite or delete historical vintages.

Deployment to an existing populated database requires a reviewed archival and
full-history rebuild plan using its actual data and backups, plus the identifier
migration above. For verification, use a separate empty database with the
standard collector schema. Do not drop an existing production table merely to
pass a check.

## Partial-release protection

All four writes — `time_series`, `original_weights`, `weights`, `metadata` —
now run inside a single `engine.begin()` transaction, after both storage guards.
On PostgreSQL (and on the SQLite database used in tests) a failure anywhere in
that block rolls the whole release back;
`tests/test_pipeline_safety.py` injects a failure after the observation write
and after the weight write and asserts that all four tables stay empty.

Databricks SQL commits each statement separately, so cross-table atomicity is
not available there. The run logs an explicit warning naming the dialect, and an
interrupted release is repaired by the next run: every upsert is idempotent and
the revision rewind re-presents the same months. Metadata is still derived from
the post-write database state inside the same transaction, so it can never
describe a partially written history.

## Verification commands

```bash
pip install -e ".[dev]"
python -m pytest -q -W ignore::DeprecationWarning
ruff check .
ruff format --check .
python -m mypy
python -m compileall -q main.py scripts tests
ONS_LIVE_TEST=1 python -m pytest tests/test_live_source.py -q -W ignore::DeprecationWarning
DATABRICKS_SQL_PARSE_TEST=1 python -m pytest tests/test_databricks_sql_grammar.py -q
python -m scripts.init_db && python main.py --no-watch --export-validation
```

Useful inspection query for current values:

```sql
SELECT series_id, reference_date, value, vintage_date, collected_at
FROM (
    SELECT series_id, reference_date, value, vintage_date, collected_at,
           ROW_NUMBER() OVER (
               PARTITION BY series_id, reference_date
               ORDER BY vintage_date DESC, collected_at DESC
           ) AS rn
    FROM collector_ons_cpi.time_series
) ranked
WHERE rn = 1;
```

## Executed verification

All rows below were executed on 2026-09-14 in this environment unless the status
says otherwise. `SKIP` always names what is missing; nothing is marked `PASS` on
the strength of a previous session.

| Gate | Status | Evidence |
| --- | --- | --- |
| Build/import | PASS | `python -m compileall -q main.py scripts tests` |
| Type check | PASS | `python -m mypy` — 44 source files, no issues, under `disallow_untyped_defs`, `warn_unreachable`, `warn_unused_ignores`, `warn_redundant_casts`, `no_implicit_optional` |
| Ruff lint | PASS | `ruff check .` — clean on ruff 0.16.7, whose default rule set is wider than the one this repository was first written against |
| Ruff format | PASS | `ruff format --check .` — 44 files already formatted |
| Tests | PASS | 335 passed, 3 skipped (the live-source and Spark-grammar suites are opt-in) |
| Live ONS source | PASS | `ONS_LIVE_TEST=1` replay against the source as published on 2026-09-14: two identical runs then an injected failure; 90,064 observations, 48,694 operational weights, 68,574 original weights, 870 metadata rows; every series' first, middle and last published value compared against the parsed source |
| Current source layout | PASS | Table 38, W1-CPI and the consumption-segment layouts all still satisfy their schema gates; see below |
| Bottom-up reconciliation | PASS | six layers, 22,018 checks, 0 failures, 100% coverage on every layer; figures below |
| Metadata audit | PASS | one series per published layer compared field by field against the live source; see below |
| PostgreSQL 16.13 | PASS | fresh DDL, full live build, unchanged second run, same-day revision, later-day revision, injected mid-persistence failure; see below |
| Idempotency | PASS | second run wrote 0 rows on all four tables and appended one `success` log |
| Vintages | PASS | historical baseline, same-day correction, later revision, latest and as-of queries; see below |
| `series_id` migration | PASS (rehearsal) / SKIP (production) | executed end to end on a real populated PostgreSQL 16.13 copy of the live build; no production database has been migrated |
| Databricks execution | SKIP | no approved Databricks workspace, host or credentials are reachable from this environment |
| Databricks SQL grammar | PASS | every emitted statement parsed by Spark 4.1.1's own SQL parser (see below) |
| Live pilot comparison | SKIP | `guimasuko/collector_template` is not reachable from this session; see below |
| Security review | PASS | see below |
| Diff review | PASS | full diff reviewed; no secret, `.env`, debug print, generated workbook or binary committed |

### Current ONS source, re-verified 2026-09-14

The 2026-09-11 evidence was not reused. The live replay was run again against
the source as published today and reproduced it exactly:

- **Table 38** — layout rows 4/5/6 still label aggregate number, CDID and name;
  all six required CDIDs (`D7BT`, `D7BU`, `D7C2`, `D7C7`, `D7F4`, `D7F5`) still
  published; 173 series and 463 months, both above their floors.
- **W1-CPI** — the header still decodes January and February–December regimes,
  the classified-row and regime floors both hold, and the overall-index row is
  exactly 1,000.000 points per thousand in every regime.
- **Consumption segments** — every published edition still carries
  `INDEX_DATE`, `CS_ID`, `CS_DESC`, `CPI_INDEX`, `CPI_WEIGHT` plus the
  `COICOP4_ID`/`COICOP5_ID` classification columns; weights still total between
  800 and 1,000 parts per thousand; 697 segments still resolve onto 85
  published Table 38 parents.
- **Latest publication recognised** — publication date parsed from the Contents
  sheet as 2026-08-19, latest reference month 2026-07-01.
- **No schema gate went stale** — every gate still fires on the current files and
  none had to be widened.

Nothing in the ONS layout changed, so no parser adaptation was required.

### Bottom-up reconciliation on the current source

| Check | Performed | Failed | Coverage | Median absolute | Maximum absolute |
| --- | ---: | ---: | ---: | ---: | ---: |
| W1 immediate-child sums | 8,436 | 0 | 1.0000 | 0.000000 | 0.000200 points per thousand |
| COICOP bottom-up, official weights | 8,251 | 0 | 1.0000 | 0.000292 pp | 0.001980 pp |
| COICOP bottom-up, operational shares | 8,251 | 0 | 1.0000 | 0.000292 pp | 0.001980 pp |
| Segment weight coverage | 1,530 | 0 | 1.0000 | 0.000500 | 7.185400 points per thousand |
| Segment bottom-up, official weights | 1,275 | 0 | 1.0000 | 0.000273 pp | 0.336575 pp |
| Segment bottom-up, operational shares | 1,275 | 0 | 1.0000 | 0.000273 pp | 0.336575 pp |

Both segment maxima remain `04.1 actual rentals for housing`, whose segment
weight coverage is 92.35% because ONS builds part of that class from
administrative rental sources it does not publish as consumption segments. That
parent is preserved, not excluded, and the tolerances still admit exactly that
documented gap. **No tolerance was changed in this pass**; every configured
value is unchanged from the previous state and each remains above the measured
maximum it has to admit.

Stored-weight invariants checked directly on the database after the run:

- all 8,251 COICOP parent-month operational share groups total `1.0` to within
  4e-16; 12,117 root rows carry exactly `1.0`;
- 0 rows in `weights` fall outside `[0, 1]`; 0 `CPI_W1_*` identifier ever
  appears in `weights`;
- `original_weights` keeps the official scale untouched — the W1 overall index
  is `1000` in both the January and the February–December 2026 regimes;
- W1 regime years are correct (Dec 2025 → 2025, Jan 2026 → 2026 at a different
  value from Feb–Dec 2026), and the consumption-segment February-to-January
  chain is correct (Jan 2026 segment weights carry base year **2025**).

### Metadata audit

One series per published layer, compared against the live source:

| Layer | series_id | Name, unit, frequency, country, native ID | First/last/count | Sampled values |
| --- | --- | --- | --- | --- |
| All items | `CPI_COICOP_ALL_D7BT` | match | 1988-01-01 … 2026-07-01, 463 | 3/3 exact |
| Division | `CPI_COICOP_D01_D7BU` | match | 1988-01-01 … 2026-07-01, 463 | 3/3 exact |
| Group | `CPI_COICOP_G011_D7C8` | match | 1988-01-01 … 2026-07-01, 463 | 3/3 exact |
| Class | `CPI_COICOP_C0111_D7D5` | match | 1988-01-01 … 2026-07-01, 463 | 3/3 exact |
| ALT aggregate | `CPI_ALT_A02_D7F4` | match | 1988-01-01 … 2026-07-01, 463 | 3/3 exact |
| Consumption segment | `CPI_CS_SEG_220107` | match | 2025-02-01 … 2026-07-01, 18 | 3/3 exact |

Every row carries `country=GBP`, `frequency=monthly`, `unit=index`,
`eco_group=consumer_prices`, `last_publish_date=2026-08-19` and the source URL of
the dataset the observation actually came from; the stored `name` is the ONS
name and the stored native identifier is the ONS CDID or CS_ID.

### PostgreSQL evidence

Executed 2026-09-14 on PostgreSQL 16.13, from an empty cluster:

- `python -m scripts.init_db` created five tables in `collector_ons_cpi` with
  `double precision`, bounded `character varying`, `date`, `timestamp` and a
  `bigint` identity key on `logs`.
- The fresh build wrote 90,064 observations, 68,574 original weights, 48,694
  operational weights and 870 metadata rows, and exited `0`.
- An immediate second run wrote **0** observations, 0 vintages, 0 operational
  weights, 0 original weights, 0 metadata inserts and 0 metadata updates, and
  appended one `success` log row (two `success` rows in total).
- **Same-day correction.** Corrupting one stored value in each of the four
  tables and re-running produced exactly one same-day `UPDATE` per table — the
  PostgreSQL `MERGE` path — repaired every value, added no rows (`time_series`
  stayed at 90,064) and left the database at a single `vintage_date`.
- **Later revision.** Backdating every vintage by three days and corrupting one
  observation produced one **new vintage row** rather than an update: 90,065
  rows across two `vintage_date` values, with the older vintage's value left
  exactly as it was. No older vintage is ever overwritten.
- **Latest and as-of queries.** The canonical latest-vintage query returns one
  row per `(series_id, reference_date)` — 90,064 rows for 90,064 distinct keys —
  and returns the corrected value. The same query with
  `WHERE vintage_date <= DATE '2026-09-12'` returns the superseded value, so the
  history is genuinely queryable as of a past date.
- **Injected mid-persistence failure.** On a separate empty database, a failure
  raised after the observation, original-weight and operational-weight writes
  returned exit code `1`, left **all four data tables empty** (the release is one
  transaction or none of it) and wrote exactly one `error` log row carrying a
  traceback.
- `log_text` truncation is visible: the error run's log ends with
  `[..., truncated ...]` at 65,535 characters.
- Output sanity on the stored database: 870 metadata rows, 0 with
  `observation_count <= 0`, 0 null first/last observations, 0 null or empty
  `source_url`, 0 duplicate `(series_id, reference_date, vintage_date)` triples,
  0 null or non-finite values, 0 operational weights outside `[0, 1]`, one
  country, one frequency, one unit and one eco_group.

### Databricks SQL: parsed by the engine's own grammar

`tests/conftest.py::emitted_sql` is the single inventory of every statement the
collector sends — 31 of them, covering the six DDL statements and every insert,
merge, update, guard and read. Two gates run over that one inventory, so a query
added to the collector cannot be reviewed by neither.

1. `tests/test_init_db_portability.py` asserts that no statement uses `SERIAL`,
   `JSONB`, `ON CONFLICT`, `RETURNING`, `ILIKE`, `DISTINCT ON`, `FILTER (`, a
   `::` cast, `DOUBLE PRECISION`, `TIMESTAMPTZ`, `NOW()` or
   `CURRENT_TIMESTAMP`; that the only inlined literals are the reviewed set
   `{'CPI%', '_', ''}`, so no value stopped travelling as a bound parameter;
   that every statement addresses only the collector schema; and that `MERGE`
   matches on the full natural key rather than relying on a primary key,
   because Databricks treats key constraints as informational.
2. `tests/test_databricks_sql_grammar.py` (opt-in, about eight seconds) parses
   all 31 statements with **Spark 4.1.1's own SQL parser**, reached through the
   `pyspark` dependency the collector already declares for token resolution.
   Databricks SQL is Spark SQL, so this replaces a reviewer's reading of the
   SQL with the engine's verdict on it. All 31 parse, including
   `BIGINT GENERATED ALWAYS AS IDENTITY`, the informational `PRIMARY KEY`
   constraints, the `MERGE ... USING (SELECT ... UNION ALL ...)` shape and the
   named `:parameter` markers. The suite includes a negative control — a
   PostgreSQL `ON CONFLICT` statement that the parser must reject — so a gate
   that silently stopped checking anything would fail.

What this does **not** prove: Unity Catalog semantics, Delta table behaviour,
permissions, or that a MERGE produces the intended rows on a real warehouse.
Those still require the Databricks execution gate below, which remains SKIP.

### Security review

- No hardcoded secret, credential or token in code, `.env.example`, tests or
  documentation; `.env` is gitignored and untracked.
- No `eval`, `exec`, `pickle`, `yaml.load`, `os.system` or `subprocess` anywhere.
- Every SQL value travels as a named parameter. The only interpolated
  identifiers are the module-level schema and table constants from
  `scripts/config.py`; no identifier is ever built from source data or user
  input.
- Every request goes through `_http_get`, which refuses any host outside
  `{www.ons.gov.uk, ons.gov.uk}`. URLs discovered in ONS pages are resolved with
  `urljoin` and then pass that allowlist, so a hostile absolute link in the page
  cannot redirect the collector elsewhere. Redirects are disabled
  (`follow_redirects=False`) and TLS verification is left on.
- Bounded timeout, bounded retries, `Retry-After` support, a rate-limit backoff
  and a maximum download size are all configured, and the body is read in chunks
  so an oversized response is refused before it is fully buffered.
- Schema gates validate every workbook and CSV layout before any value is
  trusted; an ONS rate-limit notice returned with HTTP 200 fails the gate rather
  than being parsed.
- The Databricks token is never logged; `scripts/db.py` renders the database URL
  with `hide_password=True`.
- Database work uses context-managed connections and one transaction per release.
- No `print` outside a `__main__` block; no production debug output.
- No CRITICAL or HIGH finding remains open.

## Tests

`tests/` is justified by this collector's parsing, hierarchy, vintage, weight,
mathematical-transformation, release-polling and forecast-target validation
logic. 335 committed tests cover: stable identifiers and the legacy-identifier
guard; deterministic weights-workbook selection across years, orders, absence
and rename; Table 38, W1 and consumption-segment schema drift; consumption
segment classification in both published layouts, the classification framework's
per-month validity, combined-class and split-class resolution, ambiguity and
unresolvable codes; index-without-weight and weight-without-index; the January
chain link and the February–December regime; ground-truth bottom-up
reconstruction for both layers; operational weight reproduction; original-weight
preservation and regime years; same-day and later-day vintages; two-run
idempotency; mid-persistence failure rollback; release polling and the
routing around it (an empty database builds history without entering the
watch loop, an explicit start date is anchored to the preceding December, a
populated database waits for the next expected month, and a timeout is a
successful run that writes nothing); the audit
workbook including as-of vintage selection and the empty-database case; SQL
portability and the Spark grammar; HTTP retry, rate limiting and download
bounds; engine construction and credential redaction; run-log truncation and
best-effort persistence; every spelling pandas uses for an empty workbook cell;
and the declared dependency surface.

The two worked reproductions in METHODOLOGY.md are pinned by
`tests/test_documented_examples.py`: it feeds the documented inputs through the
shipped functions and asserts the documented shares and residuals, and checks
that the published residual table still reports zero failures. A formula change
therefore cannot leave the documentation quietly wrong.

## Remaining gates

1. **Databricks execution.** Execute the DDL, MERGE, two-run and failure tests
   in an approved Databricks workspace, and confirm the Unity Catalog path,
   catalog/schema creation or the expected permission error, Delta table
   behaviour, named-parameter binding, `MERGE` row semantics and idempotency.
   **SKIP — no approved Databricks workspace, host or credentials are reachable
   from this environment.** It is never marked PASS. Everything reachable
   statically has been done instead: every emitted statement is parsed by Spark
   4.1.1's own SQL parser, and the portability gate rejects PostgreSQL-only
   syntax, unbound literals, cross-schema references and any `MERGE` that leans
   on an unenforced primary key. That narrows the open risk to runtime and
   catalog semantics, not syntax.

2. **Live pilot comparison against `guimasuko/collector_template`.**
   **SKIP — the repository is not reachable from this session.** This was
   re-attempted on 2026-09-14 and the exact failures were:
   `add_repo` refuses the attachment (`cross-tier adds are not supported in v1`,
   because the session already holds repositories owned by `lucasweber1202`);
   the GitHub API tool answers `Access denied: repository ... is not configured
   for this session`; the workspace repository listing returns no repository
   matching `template`; and an anonymous `git clone` is refused with
   `could not read Username for 'https://github.com'`. The template is therefore
   private to another owner and cannot be attached here — it is not a matter of
   having failed to look.

   What was compared instead, in full, is the authority that **is** reachable:
   `lucasweber1202/Coletores/MASTER_MACRO_COLLECTOR_GUIDELINES.md`, which the
   fleet declares the consolidated contract that overrides stale examples. The
   structural and behavioural comparison against it is recorded in "Comparison
   against the reachable fleet authority" below. `.github/` was re-diffed
   byte-for-byte against the governance repository on 2026-09-14 and every file
   under `.github/skills/` and `.github/prompts/` is identical. Re-run the
   template comparison when the repository is attachable.

3. **`series_id` migration against a production database.** The procedure is now
   executable rather than a sketch, and was rehearsed end to end on a real
   populated PostgreSQL 16.13 database (see "Rehearsal executed 2026-09-14").
   **No production database has been migrated**, so this remains an operator
   action.

4. **Legacy-weights rebuild against real pre-existing data.** A database written
   by a version that stored official points per thousand in `weights` is
   detected and refused, but the archival and full-history rebuild has not been
   executed against real legacy data.

5. **Consumption-segment history before February 2025.** ONS published item
   indices, a deeper and differently classified level, before the consumption
   segment product began. They are deliberately not stitched into the segment
   series. Extending coverage backwards is a separate, scoped decision.

6. **Intake status.** The UK CPI row in
   `lucasweber1202/Coletores/intake/collector_demands.csv` should read
   `verification` with the next action naming gates 1–4 above. That repository is
   not writable from this session (it is not attached and `add_repo` was not
   authorised for it), so the revised row is supplied in the final report for an
   operator to apply. It stays `verification` rather than `ready` precisely
   because gates 1 and 3 are unexecuted.

Because gates 1 and 3 are open, this collector must **not** be described as
"100% production-certified". It is verified end to end on PostgreSQL against the
live source; Databricks execution and the production identifier migration remain
outstanding.

### Comparison against the reachable fleet authority

Executed 2026-09-14 against `MASTER_MACRO_COLLECTOR_GUIDELINES.md` (sections 4–11
and the section 19 checklist), since the template repository itself is
unreachable. Divergences are classified, not silently normalised.

| Area | Guideline | This collector | Classification |
| --- | --- | --- | --- |
| Repository layout | `main.py` at root, flat `scripts/`, no `core/`/`lib/`/`utils/` | matches; one extra flat module `scripts/segments.py` | ACCEPTABLE LOCAL EXTENSION — a second ONS dataset with its own status, index reference and two layouts |
| Repository/schema name | `collector_<source>_<dataset>` == `SCHEMA_NAME` | `collector_ons_cpi` both | match |
| `metadata` DDL | 13 columns, PK `series_id` | identical, column for column | match |
| `time_series` DDL | 5 columns, PK `(series_id, reference_date, vintage_date)` | identical | match |
| `logs` DDL | identity `id`, bounded text | identical | match |
| 64-bit float spelling | "use the common subset" | `DOUBLE PRECISION` on PostgreSQL, `DOUBLE` on Databricks | REQUIRED SOURCE-SPECIFIC EXCEPTION — the two dialects share no spelling; `FLOAT` would silently halve precision on Databricks |
| `weights` | approved forecast-target table | present, holds operational shares | match |
| `original_weights` | PK `series_id` | PK `(series_id, reference_date, vintage_date)` | REQUIRED EXCEPTION, user-approved — a series-only key cannot hold two ONS regimes or a revision, which the guideline itself says must not be improvised away |
| Vintage semantics | insert-on-first-sight, same-day update, later revision as a new row, 10-decimal compare | implemented exactly; verified on PostgreSQL | match |
| Latest-value query | canonical `ROW_NUMBER()` form | identical, shipped in this file | match |
| Databricks engine | pilot file byte-for-byte, three-step token resolution | unchanged, and the `pyspark` guard's `type: ignore` is preserved by a targeted mypy override | match |
| Environment handling | manual `.env` parse, no `python-dotenv` | manual parse in `scripts/config.py` | match |
| Run logs | written in `main.py`'s `finally`, best-effort, truncated | match; failure to log never hides the pipeline error | match |
| Idempotency | second unchanged run writes nothing, still logs | verified: 0/0/0/0 writes, one `success` row | match |
| Release monitoring | empty DB builds now, populated DB polls, timeout is success | implemented; now covered by `tests/test_release_modes.py` | match |
| HTTP | one managed client, timeout, bounded retry/backoff, no redirects | single `http_get` with host allowlist, `Retry-After`, rate-limit backoff and a download ceiling | match |
| SQL style | `sqlalchemy.text` with named parameters, no ORM | match; the only interpolated identifiers are module constants | match |
| Dependencies | minimal, mirrored, no `requests`/`python-dotenv`/ORM/migrations | mirrored and enforced by `tests/test_dependencies.py`; none of the banned packages present | match |
| Code style | future annotations, type hints, module docstrings, no `print` | match, under `disallow_untyped_defs` | match |
| Verification loop | Phase 8 checklist | every applicable box executed above except the two open gates | match |

No DEAD/LEGACY code and no BLOCKER remains open. One drift found and fixed in
this pass is recorded below.

### Drift found and fixed on 2026-09-14

- **Lint gate was not reproducible.** `ruff` is declared as `>=0.6`, and ruff
  0.16 widened its default rule set and began linting and formatting Python
  fenced inside Markdown. A fresh environment therefore failed
  `ruff check .` on eight findings and wanted to reformat a **fleet-verbatim**
  skill file under `.github/`. The Python findings are fixed properly (import
  order, a stale `noqa`, five nested `with` statements, and one deliberately
  naive `datetime` now annotated with the reason it must stay naive); ruff is
  scoped to this repository's Python with `extend-exclude = ["*.md"]` so the
  fleet-verbatim Markdown can never be rewritten to suit a formatter. Both gates
  now pass on ruff 0.16.7.
- **A gated statement was not the executed statement.** `scripts/metadata.py`
  exposed `_SELECT_SQL` for the SQL inventory that the portability and Spark
  grammar gates read, while `upsert_metadata` executed a separately built copy
  of the same text. The two agreed today, but only one of them was ever checked.
  `upsert_metadata` now executes the inventoried object.
- **Release-mode routing was untested.** Only `_wait_for_release` itself was
  covered, so a regression that made an empty database block on the poll loop,
  or that turned a normal timeout into a failure exit, would have been silent.
  `tests/test_release_modes.py` covers the four routes; each assertion was
  confirmed to fail against a deliberately broken `main.py` before being kept.

Sources:
- [ONS CPI detailed tables](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceinflation)
- [ONS W1–W3 weights](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceinflationupdatingweightsannexatablesw1tow3)
- [ONS item/consumption-segment indices and classification frameworks](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceindicescpiandretailpricesindexrpiitemindicesandpricequotes)
- [ONS higher-level aggregation](https://www.ons.gov.uk/economy/inflationandpriceindices/methodologies/higherlevelaggregationandweightsinconsumerprices)
