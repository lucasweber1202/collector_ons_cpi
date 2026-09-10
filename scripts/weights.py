"""Persist official ONS basket weights with the same vintage semantics as observations."""

from __future__ import annotations

import logging
import math
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from scripts.config import SCHEMA_NAME, WEIGHTS_TABLE

logger = logging.getLogger(__name__)
_TABLE = f"{SCHEMA_NAME}.{WEIGHTS_TABLE}"
BATCH_SIZE = 500
ROUND_DECIMALS = 10


def _latest(engine: Engine, minimum_date: date) -> dict[tuple[str, date], dict[str, Any]]:
    sql = text(
        f"""SELECT series_id, reference_date, vintage_date, weight, collected_at
        FROM (SELECT series_id, reference_date, vintage_date, weight, collected_at,
        ROW_NUMBER() OVER (PARTITION BY series_id, reference_date
        ORDER BY vintage_date DESC, collected_at DESC) AS rn
        FROM {_TABLE} WHERE reference_date >= :minimum_date) ranked WHERE rn = 1"""
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"minimum_date": minimum_date}).mappings().all()
    result: dict[tuple[str, date], dict[str, Any]] = {}
    for row in rows:
        ref = (
            row["reference_date"].date()
            if isinstance(row["reference_date"], datetime)
            else row["reference_date"]
        )
        result[(str(row["series_id"]), ref)] = dict(row)
    return result


def upsert_weights(
    engine: Engine,
    weights_by_date: dict[date, dict[str, float]],
    collected_at: datetime | None = None,
) -> tuple[int, int]:
    """Write official weights idempotently and return ``(new, new_vintages)``."""
    collected_at = collected_at or datetime.now(UTC)
    today = collected_at.date()
    incoming: list[dict[str, Any]] = []
    for reference_date, weights in weights_by_date.items():
        for series_id, raw_weight in weights.items():
            weight = float(raw_weight)
            if math.isfinite(weight):
                incoming.append(
                    {
                        "series_id": series_id,
                        "reference_date": reference_date,
                        "weight": weight,
                        "collected_at": collected_at,
                    }
                )
    if not incoming:
        logger.info("No weight rows to upsert")
        return 0, 0
    existing = _latest(engine, min(row["reference_date"] for row in incoming))
    inserts: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    new_rows = 0
    new_vintages = 0
    for row in incoming:
        key = (row["series_id"], row["reference_date"])
        current = existing.get(key)
        if current is None:
            inserts.append({**row, "vintage_date": today})
            new_rows += 1
            continue
        if round(float(current["weight"]), ROUND_DECIMALS) == round(row["weight"], ROUND_DECIMALS):
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
        f"INSERT INTO {_TABLE} (series_id, reference_date, vintage_date, weight, collected_at) "
        "VALUES (:series_id, :reference_date, :vintage_date, :weight, :collected_at)"
    )
    update_sql = text(
        f"UPDATE {_TABLE} SET weight=:weight, collected_at=:collected_at "
        "WHERE series_id=:series_id AND reference_date=:reference_date AND vintage_date=:vintage_date"
    )
    with engine.begin() as conn:
        for start in range(0, len(inserts), BATCH_SIZE):
            conn.execute(insert_sql, inserts[start : start + BATCH_SIZE])
        for start in range(0, len(updates), BATCH_SIZE):
            conn.execute(update_sql, updates[start : start + BATCH_SIZE])
    logger.info(
        "Weights upsert: new=%d new_vintages=%d same_day_updates=%d",
        new_rows,
        new_vintages,
        len(updates),
    )
    return new_rows, new_vintages
