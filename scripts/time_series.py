"""Idempotent time-series persistence with collection-date vintage tracking."""

from __future__ import annotations

import logging
import math
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine

from scripts.config import SCHEMA_NAME, TIME_SERIES_TABLE

logger = logging.getLogger(__name__)
_TABLE = f"{SCHEMA_NAME}.{TIME_SERIES_TABLE}"
BATCH_SIZE = 500
SERIES_BATCH_SIZE = 50
ROUND_DECIMALS = 10


def get_max_reference_date(engine: Engine) -> date | None:
    """Return the latest stored reference month."""
    with engine.connect() as conn:
        value = conn.execute(text(f"SELECT MAX(reference_date) FROM {_TABLE}")).scalar()
    if isinstance(value, datetime):
        return value.date()
    return value


def get_series_aggregates(engine: Engine) -> dict[str, dict[str, Any]]:
    """Return per-series first, last, distinct count, and latest collection."""
    sql = text(
        f"""SELECT series_id, MIN(reference_date) AS first_observation,
        MAX(reference_date) AS last_observation,
        COUNT(DISTINCT reference_date) AS observation_count,
        MAX(collected_at) AS last_collected_at
        FROM {_TABLE} GROUP BY series_id"""
    )
    with engine.connect() as conn:
        rows = conn.execute(sql).mappings().all()
    return {str(row["series_id"]): dict(row) for row in rows}


def _incoming_rows(
    parsed_by_date: dict[date, dict[str, float | None]], collected_at: datetime
) -> list[dict[str, Any]]:
    """Flatten finite observations into database-shaped rows."""
    rows: list[dict[str, Any]] = []
    for reference_date, values in parsed_by_date.items():
        for series_id, raw_value in values.items():
            if raw_value is None:
                continue
            value = float(raw_value)
            if not math.isfinite(value):
                continue
            rows.append(
                {
                    "series_id": series_id,
                    "reference_date": reference_date,
                    "value": value,
                    "collected_at": collected_at,
                }
            )
    return rows


def _latest(
    engine: Engine, series_ids: list[str], minimum_date: date
) -> dict[tuple[str, date], dict[str, Any]]:
    """Fetch latest vintages for a bounded series batch."""
    sql = text(
        f"""SELECT series_id, reference_date, vintage_date, value, collected_at
        FROM (SELECT series_id, reference_date, vintage_date, value, collected_at,
        ROW_NUMBER() OVER (PARTITION BY series_id, reference_date
        ORDER BY vintage_date DESC, collected_at DESC) AS rn
        FROM {_TABLE} WHERE reference_date >= :minimum_date AND series_id IN :series_ids) ranked
        WHERE rn = 1"""
    ).bindparams(bindparam("series_ids", expanding=True))
    with engine.connect() as conn:
        rows = (
            conn.execute(sql, {"minimum_date": minimum_date, "series_ids": series_ids})
            .mappings()
            .all()
        )
    result: dict[tuple[str, date], dict[str, Any]] = {}
    for row in rows:
        ref = (
            row["reference_date"].date()
            if isinstance(row["reference_date"], datetime)
            else row["reference_date"]
        )
        result[(str(row["series_id"]), ref)] = dict(row)
    return result


def upsert_time_series(
    engine: Engine,
    parsed_by_date: dict[date, dict[str, float | None]],
    collected_at: datetime | None = None,
) -> tuple[int, int]:
    """Write new observations/revisions and return ``(new, new_vintages)``."""
    collected_at = collected_at or datetime.now(UTC)
    today = collected_at.date()
    incoming = _incoming_rows(parsed_by_date, collected_at)
    if not incoming:
        logger.info("No time-series rows to upsert")
        return 0, 0
    by_series: dict[str, list[dict[str, Any]]] = {}
    for row in incoming:
        by_series.setdefault(row["series_id"], []).append(row)
    inserts: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    new_observations = 0
    new_vintages = 0
    series_ids = sorted(by_series)
    minimum_date = min(row["reference_date"] for row in incoming)
    for start in range(0, len(series_ids), SERIES_BATCH_SIZE):
        batch_ids = series_ids[start : start + SERIES_BATCH_SIZE]
        existing = _latest(engine, batch_ids, minimum_date)
        for series_id in batch_ids:
            for row in by_series[series_id]:
                current = existing.get((series_id, row["reference_date"]))
                if current is None:
                    inserts.append({**row, "vintage_date": today})
                    new_observations += 1
                    continue
                if round(float(current["value"]), ROUND_DECIMALS) == round(
                    row["value"], ROUND_DECIMALS
                ):
                    continue
                vintage = (
                    current["vintage_date"].date()
                    if isinstance(current["vintage_date"], datetime)
                    else current["vintage_date"]
                )
                if vintage == today:
                    updates.append({**row, "vintage_date": today})
                else:
                    inserts.append({**row, "vintage_date": today})
                    new_vintages += 1

    insert_sql = text(
        f"INSERT INTO {_TABLE} (series_id, reference_date, vintage_date, value, collected_at) "
        "VALUES (:series_id, :reference_date, :vintage_date, :value, :collected_at)"
    )
    update_sql = text(
        f"UPDATE {_TABLE} SET value=:value, collected_at=:collected_at "
        "WHERE series_id=:series_id AND reference_date=:reference_date AND vintage_date=:vintage_date"
    )
    with engine.begin() as conn:
        for start in range(0, len(inserts), BATCH_SIZE):
            conn.execute(insert_sql, inserts[start : start + BATCH_SIZE])
        for start in range(0, len(updates), BATCH_SIZE):
            conn.execute(update_sql, updates[start : start + BATCH_SIZE])
    logger.info(
        "Time-series upsert: new=%d new_vintages=%d same_day_updates=%d",
        new_observations,
        new_vintages,
        len(updates),
    )
    return new_observations, new_vintages
