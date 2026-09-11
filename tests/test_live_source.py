"""Opt-in ONS source replay against a real SQLite test database.

Run: ONS_LIVE_TEST=1 python -m pytest tests/test_live_source.py -q -s
No production database is contacted and no downloaded workbook is cached.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

import main
from scripts import extract, segments
from scripts.special_aggregates import (
    EX_CPI_SPECIAL_AGGREGATES,
    collect_mm23_special_aggregates,
    complement_weight_checks,
    resolve_table38_alt_series,
)


@pytest.mark.skipif(os.getenv("ONS_LIVE_TEST") != "1", reason="explicit live-source opt-in")
def test_source_replay_twice_and_logged_failure(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    observations = extract.collect_raw_data(date(1988, 1, 1))
    basket = extract.collect_weights(date(2008, 1, 1))
    catalog = extract.get_series_catalog()

    # The ex-CPI layer is a reviewed MM23 identity map onto the Table 38 ALT
    # series already collected here. A missing CDID means ONS scope changed and
    # must be reviewed instead of silently creating or fuzzy-matching a series.
    resolved_ex_cpi, missing_ex_cpi = resolve_table38_alt_series(catalog)
    assert not missing_ex_cpi, f"MM23 ex-CPI CDIDs missing from Table 38 ALT: {missing_ex_cpi}"
    assert set(resolved_ex_cpi) == {
        row["index_cdid"] for row in EX_CPI_SPECIAL_AGGREGATES
    }

    # MM23 is validation-only at this stage: prove the reviewed columns still
    # exist and that each latest exclusion weight reconciles with the official
    # removed-component weight. Nothing from this panel is persisted here.
    mm23 = collect_mm23_special_aggregates()
    special_weight_checks = complement_weight_checks(mm23, latest_only=True)
    assert len(special_weight_checks) == len(EX_CPI_SPECIAL_AGGREGATES)
    failed_special_weights = [check for check in special_weight_checks if not check["passed"]]
    assert not failed_special_weights, f"MM23 complement weights do not sum to 1000: {failed_special_weights}"

    weight_codes = [fields["code"] for fields in extract.get_original_weight_catalog().values()]
    panel = segments.collect_segments(date(1988, 1, 1), catalog, weight_codes)

    monkeypatch.setattr(main, "_preflight", lambda: None)
    monkeypatch.setattr(main, "build_engine", lambda: engine)
    monkeypatch.setattr(main, "init_db", lambda _engine: None)
    monkeypatch.setattr(main, "collect_raw_data", lambda _start: observations)
    monkeypatch.setattr(main, "collect_weights", lambda _start: basket)
    monkeypatch.setattr(main, "collect_segments", lambda *_args: panel)

    def snapshot() -> dict[str, list[tuple[Any, ...]]]:
        """Read every persisted row so a rerun can be compared field by field."""
        ordering = {
            "time_series": "series_id, reference_date, vintage_date",
            "weights": "series_id, reference_date, vintage_date",
            "original_weights": "series_id, reference_date, vintage_date",
            "metadata": "series_id",
        }
        with engine.connect() as conn:
            return {
                table: [
                    tuple(row)
                    for row in conn.execute(
                        text(f"SELECT * FROM collector_ons_cpi.{table} ORDER BY {order}")
                    ).all()
                ]
                for table, order in ordering.items()
            }

    assert main.run(["--no-watch"]) == 0
    first = snapshot()
    assert main.run(["--no-watch"]) == 0
    assert snapshot() == first

    stored_by_series: dict[str, dict[date, float]] = {}
    for series_id, reference_date, _vintage, value, _collected in first["time_series"]:
        stored_by_series.setdefault(str(series_id), {})[reference_date] = float(value)
    source: dict[str, dict[date, float]] = {
        series_id: {
            month: float(value)
            for month, values in sorted(observations.items())
            if (value := values.get(series_id)) is not None
        }
        for series_id in catalog
    }
    source |= {
        series_id: {
            month: float(values[series_id])
            for month, values in sorted(panel.observations.items())
            if series_id in values
        }
        for series_id in panel.catalog
    }
    assert set(stored_by_series) == set(source)
    for series_id, published in source.items():
        stored = stored_by_series[series_id]
        assert len(stored) == len(published)
        months = sorted(published)
        for month in (months[0], months[len(months) // 2], months[-1]):
            assert stored[month] == published[month]

    monkeypatch.setattr(main, "collect_weights", lambda _start: {})
    assert main.run(["--no-watch"]) == 1
    assert snapshot() == first
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT status FROM collector_ons_cpi.logs ORDER BY id")
        ).scalars().all() == ["success", "success", "error"]
    print(
        "SOURCE REPLAY",
        max(observations),
        {table: len(rows) for table, rows in first.items()},
        f"segments={len(panel.catalog)}",
        f"ex_cpi={len(resolved_ex_cpi)}",
    )
