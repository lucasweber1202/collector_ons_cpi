# UK CPI guideline compliance — evidence of the current state

Baseline: `lucasweber1202/Coletores/MASTER_MACRO_COLLECTOR_GUIDELINES.md`,
SHA-256 `59739074fd125161929dda70828d7876de548ceef110dddfa7c12ec38fc9c72e`,
re-read from the live governance repository on 2026-09-14. Exceptions below are
UK-local; they do not redefine the fleet contract. Every status in this document
is `PASS`, `FAIL`, or `SKIP` with the reason stated.

## Scope: this repository is the UK CPI headline collector only

`collector_ons_cpi` collects the published UK CPI index levels, the official
basket weights and the consumption-segment layer. The CPI **exclusion special
aggregates** (the MM23 "CPI excluding ..." series) are a separate product owned
by `lucasweber1202/collector_ons_ex_cpi`. Nothing in this repository reads,
imports or depends on it, and the fleet rule against a shared core means neither
repository may grow a common package for the other.

Verified on 2026-09-14 against `origin/main`:

| Check | Result |
| --- | --- |
| MM23 special-aggregate pipeline in `main` | absent |
| EX-CPI persistence (table, column or write path) in `main` | absent |
| Special-aggregate weight registration in `main` | absent |
| Any dependency on `collector_ons_ex_cpi` | absent |
| `git log main -S MM23` | no commit ever introduced it |

The earlier branch `feature/ex-cpi-special-aggregates-mapping` and its pull
request [#7](https://github.com/lucasweber1202/collector_ons_cpi/pull/7) remain
as history. PR #7 is **closed and was never merged**, and the branch points at
the same commit as `main`, so it carries no EX-CPI commits. It must not be
merged into `main`.

### Analytical-aggregate ownership, resolved 2026-09-14

Table 38 publishes the ten exclusion aggregates in the same sheet as the
aggregates this collector owns, so until this change both products collected
them. That was duplicated **ownership**, not merely duplicated reading: two
codebases maintained the same ten ONS series, and an ONS change would have had
to be tracked in both, with no mechanism to keep them from diverging.

The split is now explicit and enforced in code. `EXCLUSION_AGGREGATE_CDIDS` in
`scripts/extract.py` names exactly ten CDIDs, which are skipped while the
Table 38 catalog is built:

| CDID | Series | Owner |
| --- | --- | --- |
| `DK9V` | CPI excluding tobacco | `collector_ons_ex_cpi` |
| `DKC5` | CPI excluding energy | `collector_ons_ex_cpi` |
| `DKC6` | Core CPI (excluding energy, food, alcohol and tobacco) | `collector_ons_ex_cpi` |
| `DKC7` | CPI excluding energy and unprocessed food | `collector_ons_ex_cpi` |
| `DKC8` | CPI excluding seasonal food | `collector_ons_ex_cpi` |
| `DKC9` | CPI excluding energy and seasonal food | `collector_ons_ex_cpi` |
| `DKD2` | CPI excluding alcohol and tobacco | `collector_ons_ex_cpi` |
| `DKD3` | CPI excluding liquid fuels, vehicle fuels and lubricants | `collector_ons_ex_cpi` |
| `DKD4` | CPI excluding housing, water, electricity, gas and other fuels | `collector_ons_ex_cpi` |
| `DKD5` | CPI excluding education, health and social protection | `collector_ons_ex_cpi` |

Everything else stays here: **41 analytical aggregates** remain, including the
structural cuts (`D7F4` All Goods, `D7F5` All Services), the goods/services
breakdowns, and the four "contributor" aggregates whose names resemble the
exclusions but are their complements rather than exclusions —
`DKD6` Energy, Food, Alcohol & Tobacco; `DKD7` Energy & Non-processed Food;
`DKD8` Energy & Seasonal Food; `DKD9` Education, Health & Social Protection.
Those four are **not** exclusion indices and were deliberately not transferred.

Why removal was safe rather than merely tidy, measured on the populated database
before the change:

- all ten were **standalone roots**: none was a reconciliation parent, none was a
  child of any parent, and no other series named one as its parent;
- none carried a W1 basket weight (0 rows in `original_weights`);
- each held only a `weight = 1.0` row in `weights`, contributing to no
  weight-sum or bottom-up check.

The reconciliation figures are byte-identical before and after the change —
8,436 / 8,251 / 8,251 / 1,530 / 1,275 / 1,275 checks, 0 failures — which is the
direct evidence that the ten contributed nothing to any validation.

Measured impact on a fresh build:

| | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Table 38 series | 173 | 163 | −10 |
| of which analytical aggregates | 51 | 41 | −10 |
| of which COICOP | 122 | 122 | 0 |
| Total series (with segments) | 870 | 860 | −10 |
| `time_series` rows | 90,064 | 85,434 | −4,630 (10 × 463) |
| `weights` rows | 48,694 | 46,464 | −2,230 (10 × 223) |
| `original_weights` rows | 68,574 | 68,574 | **0** |
| `metadata` rows | 870 | 860 | −10 |

A Table 38 carrying only *some* of the ten stops the run: that means ONS renamed
or withdrew one and the split no longer describes the source, which is a decision
rather than a silently narrower exclusion. A sheet carrying none of them is not
treated as drift, because that is a sheet which does not publish the product at
all and the required-CDID gate already decides whether such a sheet is real.

#### Cleanup plan for an already-populated database

**Nothing is deleted automatically.** A database populated before this change
still holds the ten series; the collector simply stops maintaining them, so they
freeze at their last collected vintage. That is safe but misleading, so remove
them deliberately, after confirming the consumer has moved to
`collector_ons_ex_cpi`:

```sql
-- Inspect first: exactly ten series, and what would be removed.
SELECT m.series_id, m.name, m.observation_count,
       (SELECT count(*) FROM collector_ons_cpi.time_series t WHERE t.series_id = m.series_id) AS observations,
       (SELECT count(*) FROM collector_ons_cpi.weights w WHERE w.series_id = m.series_id) AS weight_rows
FROM collector_ons_cpi.metadata m
WHERE split_part(m.series_id, '_', 4) IN
      ('DK9V','DKC5','DKC6','DKC7','DKC8','DKC9','DKD2','DKD3','DKD4','DKD5')
ORDER BY m.series_id;
```

The inspection must return exactly ten rows. If it returns more or fewer, stop:
the database does not match this reviewed set. Then, with a backup taken as in
"Step 0" below:

```sql
BEGIN;
CREATE TEMP TABLE retired_series ON COMMIT DROP AS
SELECT series_id FROM collector_ons_cpi.metadata
WHERE split_part(series_id, '_', 4) IN
      ('DK9V','DKC5','DKC6','DKC7','DKC8','DKC9','DKD2','DKD3','DKD4','DKD5');

DELETE FROM collector_ons_cpi.weights     WHERE series_id IN (SELECT series_id FROM retired_series);
DELETE FROM collector_ons_cpi.time_series WHERE series_id IN (SELECT series_id FROM retired_series);
DELETE FROM collector_ons_cpi.metadata    WHERE series_id IN (SELECT series_id FROM retired_series);
COMMIT;
```

`original_weights` is deliberately absent: these series never had a row there.
Afterwards the four counts must fall by exactly 4,630 / 2,230 / 10 and the 41
remaining analytical aggregates must be untouched. This deletion is **not**
required for the collector to run correctly; an un-cleaned database is stale in
those ten series only.

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

## Source scope and evidence (rebuilt 2026-09-14, publication stamp 19 August 2026)

Stored on a real PostgreSQL 16.13 database from a full historical build, after
the exclusion aggregates were handed to `collector_ons_ex_cpi`:

| Layer | Series | Observations | First | Last |
| --- | ---: | ---: | --- | --- |
| COICOP (all items, 12 divisions, 38 groups, 71 classes) | 122 | 54,516 | 1988-01-01 | 2026-07-01 |
| ONS analytical aggregates (exclusion indices excluded) | 41 | 18,780 | 1988-01-01 | 2026-07-01 |
| Consumption segments | 697 | 12,138 | 2025-02-01 | 2026-07-01 |
| **Total** | **860** | **85,434** | | |

Weights:

| Table | Rows | Distinct series | First | Last |
| --- | ---: | ---: | --- | --- |
| `original_weights`, W1 codes | 56,436 | 319 | 2008-01-01 | 2026-12-01 |
| `original_weights`, segment weights | 12,138 | 697 | 2025-02-01 | 2026-07-01 |
| `weights`, COICOP operational shares | 27,206 | 122 | 2008-01-01 | 2026-07-01 |
| `weights`, analytical roots at 1.0 | 9,143 | 41 | 2008-01-01 | 2026-07-01 |
| `weights`, segment operational shares | 10,115 | 697 | 2025-03-01 | 2026-07-01 |

Segment shares start in March and skip every January and February because the
January re-reference leaves those links undefined at source; no share is
invented for a month whose link does not exist.

Only 122 of the 163 Table 38 series have mapped W1 COICOP basket weights; the
41 analytical aggregates are overlapping cuts with no basket row. 192 W1
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
16.13 database** — a copy of the full live-source build described above, 860
series and 85,435 observations across two vintages — after rewriting every
identifier into the superseded name-bearing spelling:

| Step | Result |
| --- | --- |
| Detector before migration | refused the run, wrote one `error` log, wrote 0 rows |
| Step 2 collision pre-check | 0 rows |
| Step 3 apply | 860 mapped; 85,435 / 46,464 / 12,138 / 860 rows renamed |
| `CPI_W1_*` rows in `original_weights` | 56,436 before and after, untouched |
| Row counts, distinct series, distinct vintages | unchanged |
| `sum(value)` checksum | `9091180.763` before and after |
| Both vintages of a revised observation | both preserved, neither rewritten |
| Legacy rows left / orphan observations | 0 / 0 |
| `python main.py --no-watch` afterwards | exit `0`, zero writes on all four tables |

The rehearsal was re-run after the exclusion-aggregate change, so these figures
describe the procedure against the shape a production database will actually
have. **No production database has been migrated.** The rehearsal proves the
procedure on real data of the real shape; running it against production remains
an operator action with no authorised, approved production database reachable
from this environment, and gate 3 below stays open for that reason.

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
| Type check | PASS | `python -m mypy` — 45 source files, no issues, under `disallow_untyped_defs`, `warn_unreachable`, `warn_unused_ignores`, `warn_redundant_casts`, `no_implicit_optional` |
| Ruff lint | PASS | `ruff check .` — clean on ruff 0.16.7, whose default rule set is wider than the one this repository was first written against |
| Ruff format | PASS | `ruff format --check .` — 45 files already formatted |
| Tests | PASS | 340 passed, 3 skipped (the live-source and Spark-grammar suites are opt-in) |
| Live ONS source | PASS | `ONS_LIVE_TEST=1` replay against the source as published on 2026-09-14: two identical runs then an injected failure; 85,434 observations, 46,464 operational weights, 68,574 original weights, 860 metadata rows; every series' first, middle and last published value compared against the parsed source |
| Current source layout | PASS | Table 38, W1-CPI and the consumption-segment layouts all still satisfy their schema gates; see below |
| Bottom-up reconciliation | PASS | six layers, 22,018 checks, 0 failures, 100% coverage on every layer; figures below |
| Metadata audit | PASS | one series per published layer compared field by field against the live source; see below |
| PostgreSQL 16.13 | PASS | fresh DDL, full live build, unchanged second run, same-day revision, later-day revision, injected mid-persistence failure; see below |
| Idempotency | PASS | second run wrote 0 rows on all four tables and appended one `success` log |
| Vintages | PASS | historical baseline, same-day correction, later revision, latest and as-of queries; see below |
| `series_id` migration | PASS (rehearsal) / SKIP (production) | re-executed end to end on a real populated PostgreSQL 16.13 copy of the current build; no production database has been migrated |
| Databricks execution | SKIP | no approved Databricks workspace, host or credentials are reachable from this environment |
| Databricks SQL grammar | PASS | every emitted statement parsed by Spark 4.1.1's own SQL parser (see below) |
| Direct collector-template comparison | PASS | Compared `GUIDELINES.md`, `FORECAST_TARGET_GUIDELINES.md`, template tree and fleet skill/configuration structure at pinned template tree `8e4613b36c2808a7de234934a81bb26f7a22d367`; no blocker or minor drift |
| Analytical-aggregate ownership | PASS | the ten exclusion CDIDs handed to `collector_ons_ex_cpi`, 41 aggregates retained, impact measured; see above |
| Security review | PASS | see below |
| Diff review | PASS | full diff reviewed; no secret, `.env`, debug print, generated workbook or binary committed |

### Current ONS source, re-verified 2026-09-14

The 2026-09-11 evidence was not reused. The live replay was run again against
the source as published today and reproduced it exactly:

- **Table 38** — layout rows 4/5/6 still label aggregate number, CDID and name;
  all six required CDIDs (`D7BT`, `D7BU`, `D7C2`, `D7C7`, `D7F4`, `D7F5`) still
  published; 173 series published and 463 months, both above their floors. 163
  are collected here; the ten exclusion aggregates are skipped by CDID and all
  ten were present, so the ownership split still matches the source.
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
- The fresh build wrote 85,434 observations, 68,574 original weights, 46,464
  operational weights and 860 metadata rows, and exited `0`.
- An immediate second run wrote **0** observations, 0 vintages, 0 operational
  weights, 0 original weights, 0 metadata inserts and 0 metadata updates, and
  appended one `success` log row (two `success` rows in total).
- **Same-day correction.** Corrupting one stored value in each of the four
  tables and re-running produced exactly one same-day `UPDATE` per table — the
  PostgreSQL `MERGE` path — repaired every value, added no rows (`time_series`
  stayed at 85,434) and left the database at a single `vintage_date`.
- **Later revision.** Backdating every vintage by three days and corrupting one
  observation produced one **new vintage row** rather than an update: 85,435
  rows across two `vintage_date` values, with the older vintage's value left
  exactly as it was. No older vintage is ever overwritten.
- **Latest and as-of queries.** The canonical latest-vintage query returns one
  row per `(series_id, reference_date)` — 85,434 rows for 85,434 distinct keys —
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
- Output sanity on the stored database: 860 metadata rows, 0 with
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
logic. 340 committed tests cover: stable identifiers and the legacy-identifier
guard; deterministic weights-workbook selection across years, orders, absence
and rename; Table 38, W1 and consumption-segment schema drift; consumption
segment classification in both published layouts, the classification framework's
per-month validity, combined-class and split-class resolution, ambiguity and
unresolvable codes; index-without-weight and weight-without-index; the January
chain link and the February–December regime; ground-truth bottom-up
reconstruction for both layers; operational weight reproduction; original-weight
preservation and regime years; same-day and later-day vintages; two-run
idempotency; mid-persistence failure rollback; the exclusion-aggregate
ownership split, including a partially withdrawn set and a sheet that publishes
none of them; release polling and the
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

1. **Databricks execution — SKIP.** No approved workspace, host or credentials
   are available in this environment. Spark SQL grammar, portability and negative
   controls pass, but they do not substitute for real Unity Catalog execution.
2. **Production `series_id` migration — SKIP.** The reviewed migration passed
   rehearsal on a populated PostgreSQL 16.13 copy, but no authorised production
   database is reachable here.
3. **Pre-split database cleanup — OPTIONAL OPERATOR ACTION.** Databases populated
   before the ownership split may retain ten frozen EX-CPI rows. The reviewed
   inspect-first cleanup above is not a functional gate for fresh builds.
4. **Legacy transformed-weight rebuild — CONDITIONAL OPERATOR ACTION.** Only
   databases created by the retired storage model require archival/rebuild; the
   current fresh-build contract is unaffected.
5. **Pre-2025 segment history — SOURCE-SCOPE LIMITATION.** ONS did not publish
   the same consumption-segment product before its stated boundary; this is not
   treated as a failed collector gate.

The direct template comparison now passes. Because Databricks execution and the
production identifier migration remain unexecuted, this collector stays
`verification` and must not be described as ready or 100% certified.

### Structural and behavioural comparison

Executed 2026-09-14 directly against
[`guimasuko/collector_template`](https://github.com/guimasuko/collector_template)
at tree `8e4613b36c2808a7de234934a81bb26f7a22d367`, including root
`GUIDELINES.md` (blob `1bf3df07a9b81932d26571def6bf0e531b8c1464`),
`FORECAST_TARGET_GUIDELINES.md` (blob
`7ac0663c7825443e1009a18481c0b73b0184b1cd`), the repository layout and
the fleet skills/configuration structure. Source-specific differences were
judged by behaviour and contract, not visual identity. No blocker or minor drift
was found.

| Area | Template / guideline | CPI today | Classification | Action |
| --- | --- | --- | --- | --- |
| Repository name / schema | `collector_<source>_<dataset>`, `SCHEMA_NAME` identical | `collector_ons_cpi` both | MATCH | none |
| Root layout | `main.py` at root, flat `scripts/`, no `core/`/`lib/`/`utils/`/`common/` | matches exactly | MATCH | none |
| Extra module | `extract.py` under ~400 lines, split only if the source forces it and it is documented | `scripts/segments.py` is a second flat module | APPROVED / NECESSARY SOURCE-SPECIFIC EXTENSION | none — a second ONS dataset with its own statistical status, index reference and two published layouts; documented above |
| `.github/`, `.vscode/`, `.gitignore` | copied verbatim from the pilot | re-diffed byte-for-byte against the governance repository; `.github/skills/` and `.github/prompts/` identical | MATCH | none |
| `metadata` DDL | 13 columns, PK `series_id` | identical, column for column | MATCH | none |
| `time_series` DDL | 5 columns, PK `(series_id, reference_date, vintage_date)` | identical | MATCH | none |
| `logs` DDL | identity `id`, bounded text, `status` success/error | identical | MATCH | none |
| `weights` DDL | approved forecast-target table | identical | MATCH | none |
| `original_weights` DDL | PK `series_id` | PK `(series_id, reference_date, vintage_date)`, plus `weight_base_year` | APPROVED / NECESSARY SOURCE-SPECIFIC EXTENSION | none — a series-only key cannot hold two ONS regimes or a revision; §11.2 itself forbids improvising that away and requires approval, which is recorded |
| 64-bit float spelling | "common subset of both dialects" | `DOUBLE PRECISION` on PostgreSQL, `DOUBLE` on Databricks | APPROVED / NECESSARY SOURCE-SPECIFIC EXTENSION | none — the dialects share no spelling and `FLOAT` would silently halve precision on Databricks |
| Standardized columns | no unauthorized additions | none added | MATCH | none |
| Vintage semantics | first sight → today; identical → no-op; changed later → new row; changed same day → update today's row only; 10-decimal compare; drop non-finite | implemented exactly, verified on PostgreSQL | MATCH | none |
| Latest-value query | canonical `ROW_NUMBER()` form | identical, shipped in this file | MATCH | none |
| `config.py` | manual `.env` parse, no `python-dotenv`, credentials read once | matches | MATCH | none |
| `db.py` | `build_engine()`, Databricks in PROD, `pool_pre_ping`, redacted URL, no DDL | matches | MATCH | none |
| `databricks_engine.py` | pilot file byte-for-byte, three-step token resolution | unchanged; its pyspark `type: ignore` preserved by a targeted mypy override | MATCH | none |
| `init_db.py` | owns all DDL, runnable as `python -m scripts.init_db` | matches | MATCH | none |
| `extract.py` contract | `parse_series_id()`, `collect_raw_data(start_date)`, one managed client, allowlist, bounded retry | matches; `collect_weights` and the segment collector are source-specific additions | MATCH | none |
| `time_series.py` | latest-vintage fetch, 500-row multi-row batches, `get_max_reference_date`, `get_series_aggregates` | matches | MATCH | none |
| `metadata.py` | derived from parsed id + verified upstream fields, post-write aggregates, batched MERGE | matches | MATCH | none |
| `run_logs.py` | best-effort, truncated, never masks the pipeline error | matches | MATCH | none |
| `main.py` order | args → logging → preflight → engine → init_db → start date → collect → time_series → metadata → `finally` log | matches | MATCH | none |
| Series IDs | uppercase, underscore-separated coarse→fine, unique, round-trippable, no opaque native id as the whole id | `CPI_{family}_{node}_{native}` | MATCH | none |
| Controlled vocabulary | local `frozenset` validated at metadata build | `FREQUENCIES`/`UNITS`/`ECO_GROUPS` enforced | MATCH | none |
| `metadata.country` | ISO 4217 currency code | `GBP` | MATCH | none — see the currency audit below |
| Idempotency | second unchanged run writes nothing, still logs | verified 0/0/0/0 + one `success` row | MATCH | none |
| Release monitoring | empty DB builds now, populated DB polls, timeout is a logged success | implemented; covered by `tests/test_release_modes.py` | MATCH | none |
| Forecast-target weights | official weights preserved untouched, derived weights separate and reproducible | `original_weights` vs `weights`, verified on the database | MATCH | none |
| Validation workbook | sheets mirroring stored datasets | `--export-validation` produces seven sheets | MATCH | none |
| HTTP | one client, timeout, bounded retry/backoff, no arbitrary redirects, no `requests` | single `http_get` with host allowlist, `Retry-After`, rate-limit backoff, download ceiling | MATCH | none |
| SQL style | `sqlalchemy.text` + named parameters, no ORM | matches; only module constants are interpolated | MATCH | none |
| Dependencies | minimal, mirrored, no `requests`/`python-dotenv`/ORM/Alembic/Pydantic | mirrored and enforced by `tests/test_dependencies.py` | MATCH | none |
| Code style | future annotations, type hints, module docstrings, no `print`, no silent broad except | matches under `disallow_untyped_defs` | MATCH | none |
| Duplicate series | "reject duplicates" | ten exclusion aggregates were collected here **and** by `collector_ons_ex_cpi` | **GUIDELINE DRIFT** | **fixed** — handed to `collector_ons_ex_cpi` by CDID; 41 aggregates retained; see the ownership section |
| Verification loop | Phase 8 checklist | every applicable box executed; two gates remain SKIP with reasons | MATCH | none |

One GUIDELINE DRIFT was found and fixed. No BLOCKER and no DEAD/LEGACY code
remains. No APPROVED / NECESSARY SOURCE-SPECIFIC EXTENSION was removed.

**What this comparison cannot establish:** whether the template's *concrete
files* differ from the guideline text in ways the guideline does not describe —
a helper the pilot ships that this collector lacks, or a DDL detail where the
pilot and the prose disagree. The guideline states the pilot is the structural
reference and that fleet-wide files are copied from it byte-for-byte, so that
residual risk is real and is why this gate stays SKIP rather than PASS.

### Currency vocabulary audit

`metadata.country` is the **ISO 4217 currency code**, not an ISO 3166 country
code. Evidence: the master guideline's own examples are `BRL`, `USD`, `MXN`, all
currencies, and the intake backlog's column is `country_or_currency_code` with
`GBP` for UK CPI and `RUB` for Russia CPI.

This collector emits `GBP` and is correct; no change was made here. The audit
did find a governance inconsistency: `collector_ons_ex_cpi` emits `GBR`, the
ISO 3166 code for the same country, and the intake backlog recorded `GBR` for
that row. The ambiguity came from the guideline itself, which described the
field as a "currency/country code" in one place while giving only currency
examples in another. The minimal standardization was applied in the governance
repository rather than by editing another collector from here: the master
guideline now states the vocabulary is ISO 4217 and that `GBR`/`BRA`/`USA` are
not fleet values, the intake request template asks for the currency code
explicitly, and the EX-CPI intake row is corrected to `GBP` with a `next_action`
naming the constant that still has to be changed in that repository.

### Drift found and fixed on 2026-09-14

- **Duplicated ownership of the ten exclusion aggregates.** They were collected
  here and by `collector_ons_ex_cpi`, so the same ten ONS series were maintained
  by two codebases with nothing keeping them from diverging. Handed to
  `collector_ons_ex_cpi` by CDID, with the 41 other analytical aggregates
  retained and the impact measured; see the ownership section above.
- **`country` vocabulary was ambiguous fleet-wide.** The guideline called the
  field a "currency/country code" in one place and gave only currency examples
  in another, which is how `collector_ons_ex_cpi` came to emit `GBR`. Corrected
  in the governance repository; this collector's `GBP` was already right and was
  not changed.


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
