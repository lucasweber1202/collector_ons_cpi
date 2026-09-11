# collector_ons_cpi

Collects the United Kingdom Consumer Prices Index (CPI) from the Office for
National Statistics as a forecast-target series: official index levels, the
official basket weights, the derived weights needed to rebuild every published
aggregate, and a reconciliation of each aggregate against its children on every
run.

## What it collects

| Layer | Source | Series | History | Index reference |
| --- | --- | ---: | --- | --- |
| All items, COICOP divisions, groups and classes | detailed reference tables, Table 38 | 122 | Jan 1988 onwards | 2015=100 |
| ONS analytical aggregates (energy, core, goods/services cuts) | detailed reference tables, Table 38 | 51 | Jan 1988 onwards | 2015=100 |
| Consumption segments | consumption segment indices | 697 | Feb 2025 onwards | re-referenced each January |
| Official basket weights, including weight-only subclasses | Annex A table W1-CPI | 319 codes | Jan 2008 onwards | parts per 1,000 |

Consumption segments are the deepest level at which ONS publishes both an index
and a weight. COICOP subclasses have an official weight but no published index,
so their weight is preserved and no index is invented for them.

Official sources:

- [Consumer price inflation tables](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceinflation)
- [Annual CPI weights, Annex A W1-W3](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceinflationupdatingweightsannexatablesw1tow3)
- [CPI/RPI item indices, price quotes, consumption segment indices and classification frameworks](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceindicescpiandretailpricesindexrpiitemindicesandpricequotes)
- [Higher-level aggregation and weights methodology](https://www.ons.gov.uk/economy/inflationandpriceindices/methodologies/higherlevelaggregationandweightsinconsumerprices)

ONS labels both the three-decimal Table 38 indices and the consumption segment
indices as **not accredited official statistics**. That status is stored with
every series in `metadata.description` and in the audit workbook, and the two
layers are never mixed into one series.

## Output

- `metadata`: one row per series, built from the upstream ONS name,
  classification, native identifier, dataset and statistical status.
- `time_series`: official monthly index levels, vintage tracked.
- `weights`: derived local operational shares used directly for monthly
  reconstruction. A standalone root carries 1.0.
- `original_weights`: official ONS weights exactly as published, untransformed --
  W1 basket rows in parts per 1,000 (including weight-only subclasses) and
  consumption segment CPI weights -- each stamped with its published regime year.
- `logs`: one row per execution, including validation summaries.

The two weight tables are an approved UK forecast-target exception and are not
interchangeable. See [COMPLIANCE.md](COMPLIANCE.md) for the exact contract,
upgrade safeguards, evidence and remaining gates.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit COLLECTOR_DB_URL for a PostgreSQL database, or configure PROD=True.
python -m scripts.init_db
python main.py --no-watch
```

Useful queries and the current values view are in [COMPLIANCE.md](COMPLIANCE.md).

## Running modes

- **Empty database:** a full historical build, from January 1988 for Table 38
  and from the first published edition for each other layer.
- **Populated database, `python main.py`:** release monitoring. The collector
  computes the next expected month, polls the workbook's entity tag, ingests as
  soon as the release appears, and exits normally on timeout without a release.
- **`--no-watch`:** a single revision-lookback pass over the last five months,
  anchored back to the preceding December so the January chain link is
  reconcilable.
- **`--start-date`:** an explicit backfill window.
- **`--export-validation`:** also write the analyst audit workbook to
  `_verify_xls/ons_cpi_validation.xlsx`, read back from the database after the
  run has written it.

Validation always runs before persistence and a failure stops ingestion;
`--strict-validation` is retained only for CLI compatibility and cannot disable
anything.

ONS rate-limits repeated file downloads, so a full build paces its requests
(`COLLECTOR_DOWNLOAD_DELAY`) and backs off on HTTP 429
(`COLLECTOR_RATE_LIMIT_BACKOFF`), honouring `Retry-After`.

See [METHODOLOGY.md](METHODOLOGY.md) for the hierarchy, classification regimes,
aggregation formulas and reconciliation contract.
