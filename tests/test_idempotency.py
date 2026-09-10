"""Database-level regression check for no-op second writes."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, event, text

from scripts.extract import _make_series_id
from scripts.metadata import upsert_metadata
from scripts.run_logs import insert_run_log
from scripts.time_series import get_max_reference_date, upsert_time_series
from scripts.weights import upsert_weights


def _engine(tmp_path: Path):
    main_path = tmp_path / "main.db"
    schema_path = tmp_path / "collector.db"
    engine = create_engine(
        f"sqlite:///{main_path}",
        connect_args={"detect_types": sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES},
    )

    @event.listens_for(engine, "connect")
    def _attach(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute(f"ATTACH DATABASE '{schema_path}' AS collector_ons_cpi")

    with engine.begin() as conn:
        conn.execute(
            text("""CREATE TABLE collector_ons_cpi.time_series (
            series_id TEXT NOT NULL, reference_date DATE NOT NULL, vintage_date DATE NOT NULL,
            value REAL NOT NULL, collected_at TIMESTAMP NOT NULL,
            PRIMARY KEY (series_id, reference_date, vintage_date))""")
        )
        conn.execute(
            text("""CREATE TABLE collector_ons_cpi.weights (
            series_id TEXT NOT NULL, reference_date DATE NOT NULL, vintage_date DATE NOT NULL,
            weight REAL NOT NULL, collected_at TIMESTAMP NOT NULL,
            PRIMARY KEY (series_id, reference_date, vintage_date))""")
        )
        conn.execute(
            text("""CREATE TABLE collector_ons_cpi.metadata (
            series_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, country TEXT NOT NULL,
            frequency TEXT, unit TEXT, first_observation DATE, last_observation DATE,
            observation_count INTEGER NOT NULL, eco_group TEXT, source_url TEXT NOT NULL,
            last_publish_date DATE, collected_at TIMESTAMP NOT NULL)""")
        )
        conn.execute(
            text("""CREATE TABLE collector_ons_cpi.logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP NOT NULL, status TEXT NOT NULL, log_text TEXT NOT NULL,
            traceback TEXT)""")
        )
    return engine


def test_second_write_is_data_noop_and_log_is_appended(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    series_id = _make_series_id("COICOP", "ALL", "D7BT", "CPI all items")
    parsed = {date(2026, 7, 1): {series_id: 142.9}}
    weights = {date(2026, 7, 1): {series_id: 1000.0}}
    collected_at = datetime(2026, 8, 19, 7, 1)  # noqa: DTZ001 -- SQLite test adapter.

    assert upsert_time_series(engine, parsed, collected_at) == (1, 0)
    assert get_max_reference_date(engine) == date(2026, 7, 1)
    assert upsert_weights(engine, weights, collected_at) == (1, 0)
    assert upsert_metadata(engine, parsed, collected_at) == (1, 0)
    insert_run_log(engine, collected_at, collected_at, "success", "first", None)

    assert upsert_time_series(engine, parsed, collected_at) == (0, 0)
    assert upsert_weights(engine, weights, collected_at) == (0, 0)
    assert upsert_metadata(engine, parsed, collected_at) == (0, 0)
    insert_run_log(engine, collected_at, collected_at, "success", "second", None)

    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT COUNT(*) FROM collector_ons_cpi.time_series")).scalar() == 1
        )
        assert conn.execute(text("SELECT COUNT(*) FROM collector_ons_cpi.weights")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM collector_ons_cpi.metadata")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM collector_ons_cpi.logs")).scalar() == 2
