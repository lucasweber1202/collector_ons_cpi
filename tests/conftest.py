"""Shared fixtures: an isolated SQLite stand-in database and catalog builders."""

from __future__ import annotations

import io
import sqlite3
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

from scripts import extract, init_db

SCHEMA = "collector_ons_cpi"


def build_engine(tmp_path: Path) -> Engine:
    """Create the standardized tables in an attached SQLite database.

    SQLite has no CREATE SCHEMA, so the collector schema is attached under its
    production name and every other DDL statement is the shipped one.
    """
    engine = create_engine(
        f"sqlite:///{tmp_path / 'main.db'}",
        connect_args={"detect_types": sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES},
    )
    schema_path = tmp_path / "collector.db"

    @event.listens_for(engine, "connect")
    def _attach(dbapi_connection: sqlite3.Connection, _record: object) -> None:
        dbapi_connection.execute(f"ATTACH DATABASE '{schema_path}' AS {SCHEMA}")

    logs = init_db.CREATE_LOGS_TABLE.replace(
        "id BIGINT GENERATED ALWAYS AS IDENTITY", "id INTEGER PRIMARY KEY AUTOINCREMENT"
    ).replace(",\n    CONSTRAINT pk_logs PRIMARY KEY (id)", "")
    with engine.begin() as conn:
        for statement in (
            init_db.CREATE_METADATA_TABLE,
            init_db.CREATE_TIME_SERIES_TABLE.format(double="DOUBLE"),
            init_db.CREATE_WEIGHTS_TABLE.format(double="DOUBLE"),
            init_db.CREATE_ORIGINAL_WEIGHTS_TABLE.format(double="DOUBLE"),
            logs,
        ):
            conn.execute(text(statement))
    return engine


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    """Yield a disposable database carrying the shipped DDL."""
    created = build_engine(tmp_path)
    try:
        yield created
    finally:
        created.dispose()


@pytest.fixture(autouse=True)
def _isolate_extract_state() -> Iterator[None]:
    """Keep the module-level upstream caches from leaking between tests."""
    extract._SERIES_CATALOG.clear()
    extract._ORIGINAL_WEIGHTS.clear()
    extract._ORIGINAL_WEIGHT_CATALOG.clear()
    yield
    extract._SERIES_CATALOG.clear()
    extract._ORIGINAL_WEIGHTS.clear()
    extract._ORIGINAL_WEIGHT_CATALOG.clear()


def catalog_entry(
    family: str,
    node: str,
    native_id: str,
    name: str,
    *,
    classification: str = "",
    level: str = "class",
    parent: str = "",
) -> tuple[str, dict[str, str]]:
    """Build one upstream catalog row exactly as extraction would record it."""
    series_id = extract.make_series_id(family, node, native_id)
    return series_id, {
        "family": family,
        "node": node,
        "level": level,
        "native_id": native_id.upper(),
        "name": name,
        "classification": classification,
        "dataset": extract.TABLE38_DATASET,
        "source_url": extract.SOURCE_URL,
        "provenance": extract.TABLE38_PROVENANCE,
        "parent_series_id": parent,
    }


@pytest.fixture
def weights_workbook() -> Callable[[list[tuple[str, float]]], bytes]:
    """Return a builder for a minimal but layout-valid W1-CPI workbook."""

    def build(rows: list[tuple[str, float]], *, regimes: int = 12) -> bytes:
        grid: list[list[object]] = [[None] * (3 + regimes) for _ in range(4)]
        header: list[object] = [None, None, None]
        header += [f"{2015 + offset} Feb-Dec" for offset in range(regimes)]
        grid.append(header)
        grid.append([None, "CHZQ", " CPI (overall index)", *[1000.0] * regimes])
        for label, weight in rows:
            grid.append([None, "TEST", label, *[weight] * regimes])
        # Pad to the minimum classified-row count the layout gate requires.
        for index in range(len(rows), extract.WEIGHTS_MIN_ROWS):
            grid.append([None, f"P{index:03d}", f"99.9.9.{index} Padding", *[0.0] * regimes])
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame(grid).to_excel(writer, sheet_name="W1-CPI", header=False, index=False)
        return buffer.getvalue()

    return build


def month(year: int, index: int) -> date:
    """Shorthand for the first day of a month."""
    return date(year, index, 1)


def _table38_grid(
    series: list[tuple[str, str, str]], months: int, values: dict[tuple[str, int], float] | None
) -> list[list[object]]:
    """Lay out a Table 38 sheet: three header rows, then one row per month."""
    width = 2 + len(series)
    grid: list[list[object]] = [[None] * width for _ in range(4)]
    grid.append([None, "aggregate number", *[code for code, _, _ in series]])
    grid.append([None, "cdid", *[cdid for _, cdid, _ in series]])
    grid.append(["index date   ", "name", *[name for _, _, name in series]])
    for index in range(months):
        stamp = date(2016 + index // 12, index % 12 + 1, 1)
        row: list[object] = [stamp.strftime("%Y%m"), stamp]
        for _, cdid, _ in series:
            row.append(100.0 if values is None else values.get((cdid, index), 100.0 + index * 0.1))
        grid.append(row)
    return grid


@pytest.fixture
def cpi_workbook() -> Callable[..., bytes]:
    """Return a builder for a minimal but layout-valid Table 38 workbook."""

    def build(
        series: list[tuple[str, str, str]] | None = None,
        *,
        months: int = 130,
        values: dict[tuple[str, int], float] | None = None,
        code_label: str = "aggregate number",
        sheet_name: str = "Table 38",
    ) -> bytes:
        rows = series if series is not None else default_table38_series()
        grid = _table38_grid(rows, months, values)
        grid[4][1] = code_label
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame([["Publication date: 19 August 2026"]]).to_excel(
                writer, sheet_name="Contents", header=False, index=False
            )
            pd.DataFrame(grid).to_excel(writer, sheet_name=sheet_name, header=False, index=False)
        return buffer.getvalue()

    return build


def default_table38_series() -> list[tuple[str, str, str]]:
    """Anchor series plus filler, enough to clear the published-series floor."""
    series: list[tuple[str, str, str]] = [
        ("0", "D7BT", "CPI ALL ITEMS"),
        ("1", "D7BU", "FOOD AND NON-ALCOHOLIC BEVERAGES"),
        ("01.1", "D7C8", "FOOD"),
        ("01.1.1", "D7D5", "BREAD & CEREALS"),
        ("7", "D7C2", "TRANSPORT"),
        ("12", "D7C7", "MISCELLANEOUS GOODS AND SERVICES"),
        ("Agg2", "D7F4", "All Goods"),
        ("Agg20", "D7F5", "All Services"),
    ]
    # Filler divisions keep every node's parent resolvable while clearing the
    # published-series floor.
    series += [
        (str(13 + index), f"F{index:03d}", f"FILLER {index}")
        for index in range(extract.TABLE38_MIN_SERIES)
    ]
    return series
