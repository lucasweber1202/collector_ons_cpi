"""Build and idempotently upsert standardized metadata after observation writes."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import TextClause, text
from sqlalchemy.engine import Connection, Engine

from scripts.config import METADATA_TABLE, SCHEMA_NAME
from scripts.extract import (
    COUNTRY_CURRENCY,
    ECO_GROUPS,
    FREQUENCIES,
    SOURCE_URL,
    UNITS,
    get_last_publish_date,
    parse_series_id,
)
from scripts.time_series import get_series_aggregates

logger = logging.getLogger(__name__)
_TABLE = f"{SCHEMA_NAME}.{METADATA_TABLE}"
BATCH_SIZE = 500
_COMPARABLE_COLUMNS = (
    "name",
    "description",
    "country",
    "frequency",
    "unit",
    "first_observation",
    "last_observation",
    "observation_count",
    "eco_group",
    "source_url",
    "last_publish_date",
)
_COLUMNS = ("series_id", *_COMPARABLE_COLUMNS, "collected_at")
_UPDATE_COLUMNS = tuple(column for column in _COLUMNS if column != "series_id")
# See scripts/time_series.py: MERGE keeps a batch of changed rows in one
# statement; the fallback is only reached by the SQLite engine used in tests.
_MERGE_DIALECTS = frozenset({"databricks", "postgresql"})


def _batch_parameters(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten a batch into named parameters suffixed by row position."""
    return {
        f"{column}_{index}": row[column] for index, row in enumerate(rows) for column in _COLUMNS
    }


def _insert_statement(count: int) -> TextClause:
    """Build one multi-row INSERT covering ``count`` rows."""
    values = ", ".join(
        "(" + ", ".join(f":{column}_{index}" for column in _COLUMNS) + ")" for index in range(count)
    )
    return text(f"INSERT INTO {_TABLE} ({', '.join(_COLUMNS)}) VALUES {values}")


def _merge_statement(count: int) -> TextClause:
    """Build one Databricks-compatible MERGE covering ``count`` rows."""
    source = " UNION ALL ".join(
        "SELECT " + ", ".join(f":{column}_{index} AS {column}" for column in _COLUMNS)
        for index in range(count)
    )
    assignments = ", ".join(f"{column} = source.{column}" for column in _UPDATE_COLUMNS)
    return text(
        f"MERGE INTO {_TABLE} AS target USING ({source}) AS source "
        "ON target.series_id = source.series_id "
        f"WHEN MATCHED THEN UPDATE SET {assignments}"
    )


_UPDATE_SQL = text(
    f"UPDATE {_TABLE} SET {', '.join(f'{column}=:{column}' for column in _UPDATE_COLUMNS)} "
    "WHERE series_id=:series_id"
)


def _write_batches(
    conn: Connection, rows: list[dict[str, Any]], operation: str, merge: bool
) -> None:
    """Apply rows in bounded statements, logging INFO progress per batch."""
    if not rows:
        return
    logger.info("Metadata %s: writing %d rows in batches of %d", operation, len(rows), BATCH_SIZE)
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        if merge:
            conn.execute(_merge_statement(len(batch)), _batch_parameters(batch))
        elif operation == "insert":
            conn.execute(_insert_statement(len(batch)), _batch_parameters(batch))
        else:
            conn.execute(_UPDATE_SQL, batch)
        logger.info(
            "Metadata %s progress: %d/%d rows",
            operation,
            min(start + BATCH_SIZE, len(rows)),
            len(rows),
        )


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _series_descriptive_row(series_id: str) -> dict[str, object]:
    """Derive human-readable fields solely from the structured series ID."""
    _, family, node, native_id, name_slug = parse_series_id(series_id)
    official_name = name_slug.replace("_", " ").title()
    scope = "COICOP hierarchy" if family == "COICOP" else "ONS analytical aggregate"
    frequency = "monthly"
    unit = "index"
    eco_group = "consumer_prices"
    if frequency not in FREQUENCIES or unit not in UNITS or eco_group not in ECO_GROUPS:
        raise ValueError(f"Invalid controlled vocabulary for {series_id}")
    return {
        "series_id": series_id,
        "name": f"UK CPI: {official_name}",
        "description": (
            f"Official ONS Consumer Prices Index level (2015=100), {scope} node {node}; "
            f"native series identifier {native_id}."
        ),
        "country": COUNTRY_CURRENCY,
        "frequency": frequency,
        "unit": unit,
        "eco_group": eco_group,
        "source_url": SOURCE_URL,
    }


def build_metadata_rows(
    parsed_by_date: dict[date, dict[str, float | None]],
    aggregates: dict[str, dict[str, Any]],
    collected_at: datetime,
) -> list[dict[str, object]]:
    """Create one row for every extracted series present in the database."""
    series_ids = {series_id for values in parsed_by_date.values() for series_id in values}
    publish_date = get_last_publish_date()
    rows: list[dict[str, object]] = []
    for series_id in sorted(series_ids):
        aggregate = aggregates.get(series_id)
        if not aggregate:
            continue
        row = _series_descriptive_row(series_id)
        row.update(
            first_observation=_as_date(aggregate["first_observation"]),
            last_observation=_as_date(aggregate["last_observation"]),
            observation_count=int(aggregate["observation_count"]),
            last_publish_date=publish_date
            or _as_date(aggregate.get("last_collected_at"))
            or collected_at.date(),
            collected_at=collected_at,
        )
        rows.append(row)
    return rows


def upsert_metadata(
    engine: Engine,
    parsed_by_date: dict[date, dict[str, float | None]],
    collected_at: datetime | None = None,
) -> tuple[int, int]:
    """Insert new metadata and update only genuinely changed rows."""
    collected_at = collected_at or datetime.now(UTC)
    desired = build_metadata_rows(parsed_by_date, get_series_aggregates(engine), collected_at)
    logger.info("Metadata upsert: evaluating %d series", len(desired))
    with engine.connect() as conn:
        current_rows = conn.execute(text(f"SELECT * FROM {_TABLE}")).mappings().all()
    current = {str(row["series_id"]): dict(row) for row in current_rows}
    inserts: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    for row in desired:
        existing = current.get(str(row["series_id"]))
        if existing is None:
            inserts.append(row)
        elif not all(
            _as_date(existing.get(column)) == row.get(column)
            if column.endswith("observation") or column == "last_publish_date"
            else existing.get(column) == row.get(column)
            for column in _COMPARABLE_COLUMNS
        ):
            updates.append(row)
    with engine.begin() as conn:
        merge = conn.dialect.name in _MERGE_DIALECTS
        _write_batches(conn, inserts, "insert", merge=False)
        _write_batches(conn, updates, "update", merge=merge)
    logger.info("Metadata upsert: inserted=%d updated=%d", len(inserts), len(updates))
    return len(inserts), len(updates)
