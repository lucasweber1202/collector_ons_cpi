# collector_ons_cpi

Collects the United Kingdom Consumer Prices Index (CPI) from the Office for
National Statistics. It stores all 173 detailed monthly index-level series in
the ONS detailed reference table, the official CPI basket weights, and performs
hierarchy-aware bottom-up consistency checks on every run.

Official sources:

- [Consumer price inflation tables](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceinflation)
- [Annual CPI weights, Annex A W1-W3](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceinflationupdatingweightsannexatablesw1tow3)
- [Higher-level aggregation and weights methodology](https://www.ons.gov.uk/economy/inflationandpriceindices/methodologies/higherlevelaggregationandweightsinconsumerprices)

## Output

- `metadata`: one row per CPI series.
- `time_series`: official monthly index levels, vintage tracked.
- `weights`: official basket weights in parts per 1,000, monthly-expanded using
  the correct January and February-to-December regimes, vintage tracked.
- `logs`: one row per execution, including validation summaries.

The additional `weights` table is the approved forecast-target exception to the
fleet's standard three-table contract. Values are stored exactly as published;
normalization occurs only in memory during reconciliation.

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

On a populated database, `python main.py` waits for the next expected monthly
release. Use `--no-watch` for a single revision-lookback pass, `--start-date`
for a backfill, `--strict-validation` to make tolerance breaches, insufficient
reconciliation coverage, or an empty check set fatal, and
`--export-validation` to create an analyst workbook under `_verify_xls/`.

See [METHODOLOGY.md](METHODOLOGY.md) for the hierarchy and reconciliation
contract.

