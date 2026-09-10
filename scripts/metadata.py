"""Build and idempotently upsert standardized metadata after observation writes."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

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
    columns = (
        "series_id",
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
        "collected_at",
    )
    insert_sql = text(
        f"INSERT INTO {_TABLE} ({', '.join(columns)}) VALUES "
        f"({', '.join(':' + column for column in columns)})"
    )
    update_columns = tuple(column for column in columns if column != "series_id")
    update_sql = text(
        f"UPDATE {_TABLE} SET {', '.join(column + '=:' + column for column in update_columns)} "
        "WHERE series_id=:series_id"
    )
    with engine.begin() as conn:
        if inserts:
            conn.execute(insert_sql, inserts)
        if updates:
            conn.execute(update_sql, updates)
    logger.info("Metadata upsert: inserted=%d updated=%d", len(inserts), len(updates))
    return len(inserts), len(updates)
