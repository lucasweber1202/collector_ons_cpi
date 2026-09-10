"""Opt-in ONS source snapshot replay against a real SQLite test database.

Run: ONS_LIVE_TEST=1 python -m pytest tests/test_live_source.py -q -s
No production database is contacted and no downloaded workbook is cached.
"""

from __future__ import annotations

import os
from datetime import date

import pytest
from sqlalchemy import text

import main
from scripts import extract, init_db
from tests.test_idempotency import _engine


@pytest.mark.skipif(os.getenv("ONS_LIVE_TEST") != "1", reason="explicit live-source opt-in")
def test_source_snapshot_twice_and_logged_failure(tmp_path, monkeypatch) -> None:
    observations = extract.collect_raw_data(date(1988, 1, 1))
    basket = extract.collect_weights(date(2008, 1, 1))
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        conn.execute(text(init_db.CREATE_ORIGINAL_WEIGHTS_TABLE.format(double="DOUBLE")))
    monkeypatch.setattr(main, "_preflight", lambda: None)
    monkeypatch.setattr(main, "build_engine", lambda: engine)
    monkeypatch.setattr(main, "init_db", lambda _: None)
    monkeypatch.setattr(main, "collect_raw_data", lambda _: observations)
    monkeypatch.setattr(main, "collect_weights", lambda _: basket)

    def snapshot():
        with engine.connect() as conn:
            return {
                table: conn.execute(
                    text(f"SELECT * FROM collector_ons_cpi.{table} ORDER BY series_id")
                ).all()
                for table in ("time_series", "weights", "original_weights", "metadata")
            }

    assert main.run(["--no-watch"]) == 0
    first = snapshot()
    assert main.run(["--no-watch"]) == 0
    assert snapshot() == first
    latest = max(observations)
    metadata = {row[0]: row for row in first["metadata"]}
    for series_id in extract.get_series_catalog():
        assert series_id in metadata
        source = [
            (month, values[series_id])
            for month, values in sorted(observations.items())
            if values.get(series_id) is not None
        ]
        stored = {row[1]: row[3] for row in first["time_series"] if row[0] == series_id}
        for month, value in (source[0], source[len(source) // 2], source[-1]):
            assert stored[month] == value
        assert len(stored) == len(source)
    monkeypatch.setattr(main, "collect_weights", lambda _: {})
    assert main.run(["--no-watch"]) == 1
    assert snapshot() == first
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT status FROM collector_ons_cpi.logs ORDER BY id")
        ).scalars().all() == ["success", "success", "error"]
    print("SOURCE REPLAY", latest, {table: len(rows) for table, rows in first.items()})
