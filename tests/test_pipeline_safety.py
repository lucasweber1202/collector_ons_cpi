"""Validation is mandatory, and a release is never left half written."""

from __future__ import annotations

from collections import Counter
from datetime import date
from unittest.mock import Mock

import pytest
from sqlalchemy import text
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


def _wire(monkeypatch: pytest.MonkeyPatch, engine: Engine) -> None:
    """Run the real pipeline against a real database with the source stubbed."""
    monkeypatch.setattr(main, "_preflight", lambda: None)
    monkeypatch.setattr(main, "build_engine", lambda: engine)
    monkeypatch.setattr(main, "init_db", lambda _engine: None)
    monkeypatch.setattr(main, "collect_raw_data", lambda _start: OBSERVATIONS)
    monkeypatch.setattr(main, "collect_weights", lambda _start: BASKET)
    monkeypatch.setattr(main, "get_series_catalog", lambda: CATALOG)
    monkeypatch.setattr(main, "get_original_weights", dict)
    monkeypatch.setattr(main, "get_original_weight_catalog", dict)
    monkeypatch.setattr(main, "collect_segments", lambda *_args: SegmentPanel({}, {}, {}, {}))


def _counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {
            table: conn.execute(
                text(f"SELECT COUNT(*) FROM collector_ons_cpi.{table}")
            ).scalar_one()
            for table in ("time_series", "weights", "original_weights", "metadata")
        }


def test_a_complete_release_is_written(monkeypatch: pytest.MonkeyPatch, engine: Engine) -> None:
    _wire(monkeypatch, engine)
    assert main.main(main._parse_args(["--no-watch"])) == 0
    counts = _counts(engine)
    assert counts["time_series"] == 6
    assert counts["metadata"] == 3
    assert counts["weights"] == 3


def test_a_failure_after_the_observation_write_persists_nothing(
    monkeypatch: pytest.MonkeyPatch, engine: Engine
) -> None:
    """Observations, weights and metadata are one release or none of it."""
    _wire(monkeypatch, engine)
    monkeypatch.setattr(main, "upsert_metadata", Mock(side_effect=RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        main.main(main._parse_args(["--no-watch"]))
    assert _counts(engine) == {
        "time_series": 0,
        "weights": 0,
        "original_weights": 0,
        "metadata": 0,
    }


def test_a_failure_after_the_weight_write_persists_nothing(
    monkeypatch: pytest.MonkeyPatch, engine: Engine
) -> None:
    _wire(monkeypatch, engine)
    monkeypatch.setattr(main, "upsert_weights", Mock(side_effect=RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        main.main(main._parse_args(["--no-watch"]))
    assert _counts(engine)["time_series"] == 0


def test_failure_is_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = Mock()
    log = Mock()
    monkeypatch.setattr(main, "build_engine", lambda: engine)
    monkeypatch.setattr(main, "init_db", lambda _: None)
    monkeypatch.setattr(main, "insert_run_log", log)
    monkeypatch.setattr(main, "main", Mock(side_effect=ValueError("source failure")))
    assert main.run(["--no-watch"]) == 1
    assert log.call_args.args[3] == "error"
    assert "source failure" in log.call_args.args[5]
    engine.dispose.assert_called_once()


def test_validation_cannot_be_disabled(monkeypatch: pytest.MonkeyPatch, engine: Engine) -> None:
    _wire(monkeypatch, engine)
    monkeypatch.setattr(main, "validate_weight_sums", lambda *_: ([], Counter()))
    monkeypatch.setattr(main, "validate_bottom_up", lambda *_, **_kw: ([], Counter()))
    with pytest.raises(ValueError, match="Validation failed"):
        main.main(main._parse_args(["--no-watch", "--strict-validation"]))
    assert _counts(engine)["time_series"] == 0


def test_an_empty_segment_window_does_not_fake_a_pass(
    monkeypatch: pytest.MonkeyPatch, engine: Engine
) -> None:
    """A window that should contain segments must not persist without them."""
    _wire(monkeypatch, engine)
    recent = {
        date(2026, 1, 1): {PARENT: 100.0, FIRST: 100.0, SECOND: 100.0},
        date(2026, 2, 1): {PARENT: 102.5, FIRST: 110.0, SECOND: 100.0},
    }
    monkeypatch.setattr(main, "collect_raw_data", lambda _start: recent)
    monkeypatch.setattr(
        main, "collect_weights", lambda _start: {date(2026, 2, 1): BASKET[FEBRUARY]}
    )
    with pytest.raises(ValueError, match="no published edition was collected"):
        main.main(main._parse_args(["--no-watch"]))
    assert _counts(engine)["time_series"] == 0


def test_extraction_includes_december_for_january_chain() -> None:
    assert main._anchor_to_january(date(2026, 7, 1)) == date(2025, 12, 1)
