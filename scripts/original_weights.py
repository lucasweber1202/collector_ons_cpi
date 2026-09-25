"""Persist official ONS basket weights with the same vintage semantics as observations."""

from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Any

from sqlalchemy import TextClause, text
from sqlalchemy.engine import Connection

from scripts.config import (
    METADATA_TABLE,
    ORIGINAL_WEIGHTS_CATALOG_TABLE,
    ORIGINAL_WEIGHTS_TABLE,
    SCHEMA_NAME,
)

logger = logging.getLogger(__name__)
_TABLE = f"{SCHEMA_NAME}.{ORIGINAL_WEIGHTS_TABLE}"
_CATALOG_TABLE = f"{SCHEMA_NAME}.{ORIGINAL_WEIGHTS_CATALOG_TABLE}"
_METADATA_TABLE = f"{SCHEMA_NAME}.{METADATA_TABLE}"
BATCH_SIZE = 500
ROUND_DECIMALS = 10

_COLUMNS = (
    "series_id",
    "reference_date",
    "vintage_date",
    "weight",
    "collected_at",
    "weight_base_year",
)
_KEY_COLUMNS = ("series_id", "reference_date", "vintage_date")
_UPDATE_COLUMNS = ("weight", "collected_at", "weight_base_year")
# See scripts/time_series.py: MERGE keeps a batch of same-day revisions in one
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


# A MERGE's source rows are bare parameters in a SELECT, so unlike an INSERT
# there is no target column for the database to infer their type from. When the
# value is NULL, PostgreSQL types the parameter as `text` and then refuses to
# assign it to a date, numeric or timestamp column. SQLite does not care, which
# is why a SQLite-only test run never sees it and the failure lands on the first
# MERGE against a real warehouse.
#
# Casting in the source fixes it for every value, NULL included, where binding a
# parameter type does not: the driver still sends an untyped NULL. These type
# names are spelled identically in PostgreSQL and Spark SQL, and this statement
# only runs on those two -- SQLite takes the plain UPDATE path.
#
# Only nullable and date/time columns are listed. The numeric value columns are
# NOT NULL, so the database always has a real number to infer from, and the two
# dialects do not even agree on the spelling: PostgreSQL rejects DOUBLE and
# Databricks rejects DOUBLE PRECISION. See scripts/init_db.py double_type().
_MERGE_SOURCE_CASTS = {
    "reference_date": "DATE",
    "vintage_date": "DATE",
    "collected_at": "TIMESTAMP",
    "weight_base_year": "INT",
}


def _merge_source_column(column: str, index: int) -> str:
    """Render one MERGE source column, typed where the column is not a string."""
    parameter = f":{column}_{index}"
    cast = _MERGE_SOURCE_CASTS.get(column)
    expression = f"CAST({parameter} AS {cast})" if cast else parameter
    return f"{expression} AS {column}"


def _merge_statement(count: int) -> TextClause:
    """Build one Databricks-compatible MERGE covering ``count`` rows."""
    source = " UNION ALL ".join(
        "SELECT " + ", ".join(_merge_source_column(column, index) for column in _COLUMNS)
        for index in range(count)
    )
    condition = " AND ".join(f"target.{column} = source.{column}" for column in _KEY_COLUMNS)
    assignments = ", ".join(f"{column} = source.{column}" for column in _UPDATE_COLUMNS)
    return text(
        f"MERGE INTO {_TABLE} AS target USING ({source}) AS source ON {condition} "
        f"WHEN MATCHED THEN UPDATE SET {assignments}"
    )


_UPDATE_SQL = text(
    f"UPDATE {_TABLE} SET {', '.join(f'{column}=:{column}' for column in _UPDATE_COLUMNS)} "
    f"WHERE {' AND '.join(f'{column}=:{column}' for column in _KEY_COLUMNS)}"
)


def _write_batches(
    conn: Connection, rows: list[dict[str, Any]], operation: str, merge: bool
) -> None:
    """Apply rows in bounded statements, logging INFO progress per batch."""
    if not rows:
        return
    logger.info("Weights %s: writing %d rows in batches of %d", operation, len(rows), BATCH_SIZE)
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        if merge:
            conn.execute(_merge_statement(len(batch)), _batch_parameters(batch))
        elif operation == "insert":
            conn.execute(_insert_statement(len(batch)), _batch_parameters(batch))
        else:
            conn.execute(_UPDATE_SQL, batch)
        logger.info(
            "Weights %s progress: %d/%d rows",
            operation,
            min(start + BATCH_SIZE, len(rows)),
            len(rows),
        )


_LATEST_SQL = text(
    f"""SELECT series_id, reference_date, vintage_date, weight, weight_base_year, collected_at
    FROM (SELECT series_id, reference_date, vintage_date, weight, weight_base_year, collected_at,
    ROW_NUMBER() OVER (PARTITION BY series_id, reference_date
    ORDER BY vintage_date DESC, collected_at DESC) AS rn
    FROM {_TABLE} WHERE reference_date >= :minimum_date) ranked WHERE rn = 1"""
)


def _latest(conn: Connection, minimum_date: date) -> dict[tuple[str, date], dict[str, Any]]:
    """Fetch the latest stored vintage per series and month."""
    rows = conn.execute(_LATEST_SQL, {"minimum_date": minimum_date}).mappings().all()
    result: dict[tuple[str, date], dict[str, Any]] = {}
    for row in rows:
        ref = (
            row["reference_date"].date()
            if isinstance(row["reference_date"], datetime)
            else row["reference_date"]
        )
        result[(str(row["series_id"]), ref)] = dict(row)
    return result


def upsert_original_weights(
    conn: Connection,
    rows: list[dict[str, Any]],
    collected_at: datetime,
) -> tuple[int, int]:
    """Write official weights idempotently and return ``(new, new_vintages)``.

    Each row states its own ``weight_base_year``. The two ONS weight products
    run different annual regimes -- W1 labels January and February-December of
    one calendar year, while a consumption-segment basket runs February to the
    following January -- so the regime year cannot be inferred from the
    reference month here.
    """
    today = collected_at.date()
    incoming: list[dict[str, Any]] = []
    for row in rows:
        weight = float(row["weight"])
        if math.isfinite(weight):
            incoming.append(
                {
                    "series_id": row["series_id"],
                    "reference_date": row["reference_date"],
                    "weight": weight,
                    "collected_at": collected_at,
                    "weight_base_year": int(row["weight_base_year"]),
                }
            )
    logger.info("Weights upsert: evaluating %d incoming weights", len(incoming))
    if not incoming:
        logger.info("No weight rows to upsert")
        return 0, 0
    existing = _latest(conn, min(row["reference_date"] for row in incoming))
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
        # The published regime year is part of the official record, so a
        # corrected regime is a real change even when the value is unchanged.
        if (
            round(float(current["weight"]), ROUND_DECIMALS) == round(row["weight"], ROUND_DECIMALS)
            and int(current["weight_base_year"]) == row["weight_base_year"]
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
    merge = conn.dialect.name in _MERGE_DIALECTS
    _write_batches(conn, inserts, "insert", merge=False)
    _write_batches(conn, updates, "same-day update", merge=merge)
    logger.info(
        "Weights upsert: new=%d new_vintages=%d same_day_updates=%d",
        new_rows,
        new_vintages,
        len(updates),
    )
    return new_rows, new_vintages


# -- the weight-only identity crosswalk ------------------------------------
#
# Table 38 indexes COICOP down to class level. The W1 workbook publishes
# weights below that, and for two analytical totals the index set does not
# carry, so `original_weights` holds more distinct series_ids than `metadata`
# does. That is the source's shape, not a defect: a published weight is part of
# the official record and is stored unmodified under the identity the workbook
# gives it.
#
# What must not happen is that those identities stay unexplained. This table
# names every one of them -- its classification code, its published label, its
# CDID where the source gives one, and the Table 38 series it maps to, or NULL
# when the source publishes no index at that level. An auditor can then join
# `original_weights` to it and account for every row, instead of finding
# several hundred identifiers with nothing to join to.

_CATALOG_COLUMNS = (
    "series_id",
    "classification_code",
    "name",
    "native_id",
    "mapped_series_id",
    "dataset",
    "source_url",
    "collected_at",
)
_CATALOG_UPDATE_COLUMNS = tuple(column for column in _CATALOG_COLUMNS if column != "series_id")

_CATALOG_SELECT_SQL = text(f"SELECT {', '.join(_CATALOG_COLUMNS)} FROM {_CATALOG_TABLE}")
_CATALOG_INSERT_SQL = text(
    f"INSERT INTO {_CATALOG_TABLE} ({', '.join(_CATALOG_COLUMNS)}) "
    f"VALUES ({', '.join(f':{column}' for column in _CATALOG_COLUMNS)})"
)
_CATALOG_UPDATE_SQL = text(
    f"UPDATE {_CATALOG_TABLE} SET "
    f"{', '.join(f'{column}=:{column}' for column in _CATALOG_UPDATE_COLUMNS)} "
    "WHERE series_id=:series_id"
)


def _catalog_row(series_id: str, fields: dict[str, str], collected_at: datetime) -> dict[str, Any]:
    """Shape one workbook catalog entry into a crosswalk row."""
    return {
        "series_id": series_id,
        "classification_code": fields["code"],
        "name": fields["name"],
        "native_id": fields.get("native_id") or None,
        "mapped_series_id": fields.get("mapped_series_id") or None,
        "dataset": fields["dataset"],
        "source_url": fields["source_url"],
        "collected_at": collected_at,
    }


def upsert_original_weight_catalog(
    conn: Connection,
    catalog: dict[str, dict[str, str]],
    collected_at: datetime,
) -> tuple[int, int]:
    """Write the crosswalk idempotently and return ``(inserted, updated)``.

    A row is rewritten only when the source's own description of the identity
    changed, so an unchanged rerun touches nothing. The crosswalk carries no
    vintage: it describes what an identifier means, not an observed value.
    """
    if not catalog:
        return 0, 0
    existing = {
        str(row["series_id"]): dict(row)
        for row in conn.execute(_CATALOG_SELECT_SQL).mappings().all()
    }
    inserts: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    for series_id, fields in sorted(catalog.items()):
        row = _catalog_row(series_id, fields, collected_at)
        current = existing.get(series_id)
        if current is None:
            inserts.append(row)
            continue
        if any(current.get(column) != row[column] for column in _CATALOG_UPDATE_COLUMNS[:-1]):
            updates.append(row)
    logger.info(
        "Original weight catalog: %d entries, %d new, %d changed",
        len(catalog),
        len(inserts),
        len(updates),
    )
    for start in range(0, len(inserts), BATCH_SIZE):
        conn.execute(_CATALOG_INSERT_SQL, inserts[start : start + BATCH_SIZE])
    for start in range(0, len(updates), BATCH_SIZE):
        conn.execute(_CATALOG_UPDATE_SQL, updates[start : start + BATCH_SIZE])
    return len(inserts), len(updates)


_UNDOCUMENTED_SQL = text(
    f"SELECT DISTINCT weights.series_id FROM {_TABLE} weights "
    f"LEFT JOIN {_CATALOG_TABLE} crosswalk ON crosswalk.series_id = weights.series_id "
    f"LEFT JOIN {_METADATA_TABLE} series ON series.series_id = weights.series_id "
    "WHERE crosswalk.series_id IS NULL AND series.series_id IS NULL"
)

_DANGLING_MAPPING_SQL = text(
    f"SELECT crosswalk.series_id, crosswalk.mapped_series_id FROM {_CATALOG_TABLE} crosswalk "
    f"LEFT JOIN {_METADATA_TABLE} series ON series.series_id = crosswalk.mapped_series_id "
    "WHERE crosswalk.mapped_series_id IS NOT NULL AND series.series_id IS NULL"
)

# Two workbook codes may legitimately claim one index series: COICOP division
# 10 has a single group, so W1 lists Education as both `10` and `10.0`, under
# the same CDID and with the same weight in every month. That is one published
# series shown at two classification levels, not two weights to add up.
#
# What must never pass is a collision that is not that: codes carrying
# different CDIDs, or carrying weights that disagree in any month. Either would
# double count the series' official weight, and neither can be told from the
# benign case by counting claimants alone.
_COLLIDING_MAPPING_SQL = text(
    "SELECT first.series_id, second.series_id, first.mapped_series_id "
    f"FROM {_CATALOG_TABLE} first JOIN {_CATALOG_TABLE} second "
    "  ON second.mapped_series_id = first.mapped_series_id "
    "  AND second.series_id > first.series_id "
    "WHERE first.mapped_series_id IS NOT NULL "
    "  AND (COALESCE(first.native_id, '') <> COALESCE(second.native_id, '') "
    "       OR EXISTS (SELECT 1 "
    f"                 FROM {_TABLE} left_weight JOIN {_TABLE} right_weight "
    "                   ON right_weight.reference_date = left_weight.reference_date "
    "                   AND right_weight.vintage_date = left_weight.vintage_date "
    "                 WHERE left_weight.series_id = first.series_id "
    "                   AND right_weight.series_id = second.series_id "
    "                   AND left_weight.weight <> right_weight.weight))"
)


def assert_weight_identity_contract(conn: Connection) -> None:
    """Refuse to finish a run that leaves a weight identity unaccounted for.

    Three ways the contract can break, all of them checked inside the write
    transaction so a violation rolls the run back rather than being discovered
    in the warehouse:

    * a weight whose identity is neither a real series nor a documented
      weight-only code -- the orphan the crosswalk exists to rule out;
    * a crosswalk entry pointing at a Table 38 series that is not stored, which
      is what a renamed or filtered-away index looks like;
    * two workbook codes claiming the same index series with different CDIDs or
      disagreeing weights, which would double count that series' official
      weight. One published series listed at two classification levels -- same
      CDID, same weight every month -- is the source's own shape and passes.
    """
    undocumented = [str(row[0]) for row in conn.execute(_UNDOCUMENTED_SQL)]
    if undocumented:
        raise ValueError(
            f"{len(undocumented)} weight identities are neither stored series nor documented "
            f"weight-only codes, e.g. {sorted(undocumented)[:5]}"
        )
    dangling = [(str(row[0]), str(row[1])) for row in conn.execute(_DANGLING_MAPPING_SQL)]
    if dangling:
        raise ValueError(f"Crosswalk maps weights onto series that are not stored: {dangling[:5]}")
    colliding = [
        (str(row[0]), str(row[1]), str(row[2])) for row in conn.execute(_COLLIDING_MAPPING_SQL)
    ]
    if colliding:
        raise ValueError(
            f"Workbook codes disagree while claiming the same index series: {colliding[:5]}"
        )
