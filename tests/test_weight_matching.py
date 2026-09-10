"""Regression tests for W1 weight attribution: duplicates, conflicts, ambiguity."""

from __future__ import annotations

import io
import logging
from datetime import date

import pandas as pd
import pytest

from scripts.extract import _make_series_id, parse_weights_workbook

EDUCATION = _make_series_id("COICOP", "D10", "D7C5", "Education")
HEALTH = _make_series_id("COICOP", "D06", "D7BX", "Health")
CATALOG = {
    EDUCATION: {"family": "COICOP", "node": "D10", "native_id": "D7C5", "name": "EDUCATION"},
    HEALTH: {"family": "COICOP", "node": "D06", "native_id": "D7BX", "name": "HEALTH"},
}


def _workbook(rows: list[tuple[str, float]]) -> bytes:
    """Build a minimal W1-CPI sheet: header block, then one label/weight per row."""
    grid: list[list[object]] = [[None] * 4 for _ in range(4)]
    grid.append([None, None, None, "2026 Feb-Dec"])
    for label, weight in rows:
        grid.append([None, None, label, weight])
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(grid).to_excel(writer, sheet_name="W1-CPI", header=False, index=False)
    return buffer.getvalue()


def test_agreeing_duplicate_rows_are_reported_but_keep_the_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two rows for one series must be surfaced even when the values agree."""
    blob = _workbook([("10 Education", 34.2466), ("10.0 Education", 34.2466)])

    with caplog.at_level(logging.WARNING, logger="scripts.extract"):
        parsed = parse_weights_workbook(blob, CATALOG)

    assert parsed[date(2026, 6, 1)][EDUCATION] == pytest.approx(34.2466)
    assert any("both map to" in r.getMessage() for r in caplog.records)
    assert not any("Conflicting W1 weights" in r.getMessage() for r in caplog.records)


def test_conflicting_duplicate_rows_are_reported(caplog: pytest.LogCaptureFixture) -> None:
    """Disagreeing duplicates make the stored weight depend on row order."""
    blob = _workbook([("10 Education", 34.2466), ("10.0 Education", 99.9999)])

    with pytest.raises(ValueError, match="Conflicting W1 weights"):
        parse_weights_workbook(blob, CATALOG)


def test_unmatched_row_is_reported_and_dropped(caplog: pytest.LogCaptureFixture) -> None:
    """A W1 row with no Table 38 counterpart is an exception, not silent noise."""
    blob = _workbook([("10 Education", 34.2466), ("10.4 Tertiary education", 5.0)])

    with caplog.at_level(logging.WARNING, logger="scripts.extract"):
        parsed = parse_weights_workbook(blob, CATALOG)

    assert set(parsed[date(2026, 6, 1)]) == {EDUCATION}
    assert any("matched no Table 38 series" in r.getMessage() for r in caplog.records)


def test_start_date_still_filters_expanded_months() -> None:
    """The regime expansion keeps honouring the extraction window."""
    blob = _workbook([("10 Education", 34.2466)])

    parsed = parse_weights_workbook(blob, CATALOG, start_date=date(2026, 7, 1))

    assert min(parsed) == date(2026, 7, 1)
    assert max(parsed) == date(2026, 12, 1)
