# Standalone portability

Verified 2026-09-16. This repository contains all runtime code, dependencies,
tests and configuration needed by the ONS CPI collector. No sibling repository,
submodule, symlink or external `PYTHONPATH` is required.

## Corporate Windows quickstart

```powershell
git clone https://github.com/lucasweber1202/collector_ons_cpi.git
Set-Location collector_ons_cpi
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m pytest -q
ruff check .
mypy .
python main.py --once
```

Supported Python: 3.11 and 3.12. Local execution requires `PROD=false` and
`COLLECTOR_DB_URL` for PostgreSQL. Databricks is optional and selected only by
`PROD=true`; it then requires `DBX_SERVER_HOSTNAME`, `DBX_HTTP_PATH`, and either
`DATABRICKS_TOKEN` or Azure Key Vault configuration. Imports require none of
these values.

Network: HTTPS to `www.ons.gov.uk`/`ons.gov.uk`; PostgreSQL host in
`COLLECTOR_DB_URL`; Databricks/Azure hosts only in production mode. TLS remains
enabled. Corporate custom CAs may be supplied through `SSL_CERT_FILE` or
`REQUESTS_CA_BUNDLE`; never commit a private CA.

Writes: configured database and repository-local `_verify_xls/` when exporting
validation workbooks. `.env`, virtualenvs, caches and generated workbooks are
gitignored.

Certification: standalone code PASS; sibling required NO; personal absolute
path NO; Databricks required NO; external database required for collection YES.
