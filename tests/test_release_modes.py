"""How a run chooses between a historical build, a rewind and release monitoring.

The guideline fixes this routing: an empty database builds history immediately
and must never block on the poll loop, a populated database waits for the next
expected month, and a timeout without a release is a normal successful outcome.
Only ``_wait_for_release`` itself was covered before, so a regression in the
routing around it would have been silent.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pytest
from sqlalchemy.engine import Engine

import main
from scripts.segments import SegmentPanel
from tests.conftest import catalog_entry

_PARENT = catalog_entry("COICOP", "ALL", "D7BT", "CPI ALL ITEMS", level="all_items")
_FIRST = catalog_entry(
    "COICOP", "D01", "D7BU", "First division", level="division", parent=_PARENT[0]
)
_SECOND = catalog_entry(
    "COICOP", "D02", "D7BV", "Second division", level="division", parent=_PARENT[0]
)
PARENT, FIRST, SECOND = _PARENT[0], _FIRST[0], _SECOND[0]
CATALOG = dict([_PARENT, _FIRST, _SECOND])

JANUARY, FEBRUARY = date(2024, 1, 1), date(2024, 2, 1)
OBSERVATIONS: dict[date, dict[str, float | None]] = {
    JANUARY: {PARENT: 100.0, FIRST: 100.0, SECOND: 100.0},
    FEBRUARY: {PARENT: 102.5, FIRST: 110.0, SECOND: 100.0},
}
BASKET = {FEBRUARY: {PARENT: 1000.0, FIRST: 250.0, SECOND: 750.0}}


def _wire(monkeypatch: pytest.MonkeyPatch, engine: Engine) -> list[date | None]:
    """Run the real pipeline against a real database, recording each download."""
    starts: list[date | None] = []

    def fake_collect(start_date: date | None = None) -> dict[date, dict[str, float | None]]:
        starts.append(start_date)
        return OBSERVATIONS

    monkeypatch.setattr(main, "_preflight", lambda: None)
    monkeypatch.setattr(main, "build_engine", lambda: engine)
    monkeypatch.setattr(main, "init_db", lambda _engine: None)
    monkeypatch.setattr(main, "collect_raw_data", fake_collect)
    monkeypatch.setattr(main, "collect_weights", lambda _start: BASKET)
    monkeypatch.setattr(main, "get_series_catalog", lambda: CATALOG)
    monkeypatch.setattr(main, "get_original_weights", dict)
    monkeypatch.setattr(main, "get_original_weight_catalog", dict)
    monkeypatch.setattr(main, "collect_segments", lambda *_args: SegmentPanel({}, {}, {}, {}))
    return starts


def _forbid_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any entry into the watch loop an immediate, visible failure."""

    def never(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the watch loop must not run for this invocation")

    monkeypatch.setattr(main, "_wait_for_release", never)
    monkeypatch.setattr(main.time, "sleep", never)


def test_an_empty_database_builds_history_without_polling(
    monkeypatch: pytest.MonkeyPatch, engine: Engine
) -> None:
    """A first deployment must populate history now, not wait out a release window."""
    starts = _wire(monkeypatch, engine)
    _forbid_polling(monkeypatch)

    assert main.main(main._parse_args([])) == 0
    assert starts == [main.DEFAULT_START_DATE]


def test_an_explicit_start_date_never_polls(
    monkeypatch: pytest.MonkeyPatch, engine: Engine
) -> None:
    """``--start-date`` is a backfill window, anchored to the preceding December."""
    starts = _wire(monkeypatch, engine)
    _forbid_polling(monkeypatch)

    assert main.main(main._parse_args(["--start-date", "2024-03-01"])) == 0
    assert starts == [date(2023, 12, 1)]


def test_a_populated_database_without_no_watch_enters_release_monitoring(
    monkeypatch: pytest.MonkeyPatch, engine: Engine
) -> None:
    """Once history exists, a bare run waits for the next expected month."""
    starts = _wire(monkeypatch, engine)
    assert main.main(main._parse_args(["--no-watch"])) == 0
    assert starts == [main.DEFAULT_START_DATE]

    watched: list[date] = []

    def fake_wait(latest: date) -> None:
        watched.append(latest)

    monkeypatch.setattr(main, "_wait_for_release", fake_wait)

    assert main.main(main._parse_args([])) == 0
    assert watched == [FEBRUARY]


def test_a_release_timeout_is_a_successful_run_that_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, engine: Engine
) -> None:
    """Timing out without a release is normal: exit 0, one success log, no writes."""
    _wire(monkeypatch, engine)
    assert main.run(["--no-watch"]) == 0

    monkeypatch.setattr(main, "_wait_for_release", lambda _latest: None)
    assert main.run([]) == 0

    from sqlalchemy import text

    with engine.connect() as conn:
        statuses: Sequence[str] = (
            conn.execute(text("SELECT status FROM collector_ons_cpi.logs ORDER BY id"))
            .scalars()
            .all()
        )
        observations: int = conn.execute(
            text("SELECT COUNT(*) FROM collector_ons_cpi.time_series")
        ).scalar_one()
    assert statuses == ["success", "success"]
    assert observations == 6
