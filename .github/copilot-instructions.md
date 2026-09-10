# Collector instructions

This is a self-contained forecast-target collector following the fleet contract
in `lucasweber1202/Coletores/MASTER_MACRO_COLLECTOR_GUIDELINES.md`.

- Keep the repository flat and source-specific; do not add shared core classes,
  ORM models, migrations, `requests`, or `python-dotenv`.
- Preserve the standardized `metadata`, `time_series`, and `logs` schemas.
- `weights` is the approved source-forced exception and stores official ONS
  weights unchanged with vintage tracking.
- Keep structured, uppercase, round-trippable `series_id` values.
- Preserve idempotency: an unchanged second run writes no metadata, observation,
  or weight rows, but does write one successful log row.
- Verify endpoints and workbook layouts against current official ONS sources.
- Run the verification loop before every PR.

