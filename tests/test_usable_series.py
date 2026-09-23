"""GUIDELINES 5.1 on a forecast target, where a wrong drop corrupts the target.

These tests are adversarial on purpose. The dangerous failure here is not a
dead series surviving; it is a live one being deleted, because the basket is
what the collector exists to publish. The cases below therefore spend most of
their effort proving the filter does NOT fire.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

import pytest

from scripts.usable_series import (
    UsabilityReport,
    apply_usable_series_filter,
    classify_series,
)

LATEST = date(2026, 8, 1)

# Sequence/Mapping rather than list/dict: the element type is float | None and
# the literals below are all float, which invariant containers reject.
Points = Sequence[tuple[date, float | None]]


def _months(start: date, count: int) -> list[date]:
    out = []
    year, month = start.year, start.month
    for _ in range(count):
        out.append(date(year, month, 1))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def _series(spec: Mapping[str, Points]) -> dict[date, dict[str, float | None]]:
    observations: dict[date, dict[str, float | None]] = {}
    for series_id, points in spec.items():
        for month, value in points:
            observations.setdefault(month, {})[series_id] = value
    return observations


def _live(series_id: str, months: int = 24) -> dict[str, Points]:
    span = _months(date(2024, 9, 1), months)
    return {series_id: [(m, 100.0 + i) for i, m in enumerate(span)]}


# -- the filter must not fire on legitimate series -------------------------


def test_a_long_running_series_is_kept() -> None:
    report = classify_series(_series(_live("LONG", 24)), {}, latest_period=LATEST)
    assert report.kept == ("LONG",)
    assert report.dropped == ()


def test_a_valid_recently_rebased_series_is_kept() -> None:
    """The 681-series case: born partway through the window, still printing.

    A minimum-history rule would delete these. There is deliberately no such
    rule, and this test is what stops one being added casually.
    """
    recent = {"NEWCLASS": [(m, 100.0) for m in _months(date(2026, 6, 1), 3)]}
    report = classify_series(_series(recent), {}, latest_period=LATEST)
    assert report.kept == ("NEWCLASS",)
    assert report.dropped == ()


def test_a_single_observation_series_at_the_edge_is_kept() -> None:
    """One print, this month. Short is not the same as dead."""
    report = classify_series(_series({"BRANDNEW": [(LATEST, 100.0)]}), {}, latest_period=LATEST)
    assert report.kept == ("BRANDNEW",)


def test_an_irregular_series_with_gaps_is_kept_if_it_still_prints() -> None:
    sparse = {"IRREG": [(date(2025, 2, 1), 100.0), (date(2026, 1, 1), 101.0), (LATEST, 102.0)]}
    report = classify_series(_series(sparse), {}, latest_period=LATEST)
    assert report.kept == ("IRREG",)


def test_recent_nulls_do_not_kill_a_series_whose_last_real_print_is_recent() -> None:
    spec = {"TRAILNULL": [(date(2026, 6, 1), 100.0), (date(2026, 7, 1), None), (LATEST, None)]}
    report = classify_series(_series(spec), {}, latest_period=LATEST)
    assert report.kept == ("TRAILNULL",)


# -- the filter must fire on genuinely dead series -------------------------


def test_a_retired_series_is_dropped() -> None:
    """The 16-segment case: stopped 7 months back, no current weight."""
    spec = {"RETIRED": [(m, 100.0) for m in _months(date(2025, 2, 1), 12)]}
    report = classify_series(_series(spec), {}, latest_period=LATEST)
    assert report.stale == ("RETIRED",)
    assert report.kept == ()


def test_padded_nulls_cannot_disguise_a_dead_series() -> None:
    """Trailing nulls up to the current month must not read as 'live'.

    Staleness is measured on the last non-null print, so a publisher that pads
    a retired series with empty cells to the edge of the file is still caught.
    """
    dead: list[tuple[date, float | None]] = [(m, 100.0) for m in _months(date(2025, 2, 1), 12)]
    padding: list[tuple[date, float | None]] = [(m, None) for m in _months(date(2026, 2, 1), 7)]
    report = classify_series(_series({"PADDED": dead + padding}), {}, latest_period=LATEST)
    assert report.stale == ("PADDED",)


def test_an_all_null_stub_is_dropped_as_empty_not_stale() -> None:
    stub = {"STUB": [(m, None) for m in _months(date(2026, 1, 1), 8)]}
    report = classify_series(_series(stub), {}, latest_period=LATEST)
    assert report.empty == ("STUB",)
    assert report.stale == ()


# -- the safety property ---------------------------------------------------


def test_a_weighted_series_is_never_dropped_however_stale() -> None:
    """The property that makes the filter unable to break the basket."""
    spec = {"WEIGHTED": [(m, 100.0) for m in _months(date(2024, 1, 1), 6)]}
    weights = {LATEST: {"WEIGHTED": 0.5}}
    report = classify_series(_series(spec), weights, latest_period=LATEST)
    assert report.kept == ("WEIGHTED",)
    assert report.dropped == ()
    assert report.protected_by_weight == ("WEIGHTED",)


def test_a_weight_in_an_old_regime_does_not_protect_a_dead_series() -> None:
    """Protection tracks the *current* regime, not any historical weight."""
    spec = {"OLD": [(m, 100.0) for m in _months(date(2025, 2, 1), 12)]}
    weights = {date(2025, 2, 1): {"OLD": 0.5}, LATEST: {"OTHER": 0.5}}
    report = classify_series(_series(spec), weights, latest_period=LATEST)
    assert report.stale == ("OLD",)


# -- threshold boundaries --------------------------------------------------


@pytest.mark.parametrize(
    ("last_print", "expected_kept"),
    [
        (date(2026, 2, 1), True),  # exactly 6 months stale -> at the limit, kept
        (date(2026, 1, 1), False),  # 7 months -> over the limit, dropped
    ],
)
def test_the_staleness_boundary_is_inclusive(last_print: date, expected_kept: bool) -> None:
    spec = {"EDGE": [(last_print, 100.0)]}
    report = classify_series(_series(spec), {}, latest_period=LATEST, max_stale_months=6)
    assert (report.kept == ("EDGE",)) is expected_kept


# -- every persisted layer is pruned with one key set ----------------------


def test_dropping_a_series_prunes_every_layer_consistently() -> None:
    observations = _series(
        {
            "LIVE": [(LATEST, 100.0)],
            "DEAD": [(date(2025, 2, 1), 100.0)],
        }
    )
    operational = {LATEST: {"LIVE": 1.0}}
    original_rows = [
        {"series_id": "LIVE", "reference_date": LATEST, "weight": 500.0},
        {"series_id": "DEAD", "reference_date": date(2025, 2, 1), "weight": 500.0},
    ]
    catalog = {"LIVE": {"name": "live"}, "DEAD": {"name": "dead"}}

    obs, weights, rows, cat, report = apply_usable_series_filter(
        observations, operational, original_rows, catalog, latest_period=LATEST
    )

    assert report.stale == ("DEAD",)
    surviving = {sid for values in obs.values() for sid in values}
    assert surviving == {"LIVE"}
    assert all("DEAD" not in values for values in weights.values())
    assert [row["series_id"] for row in rows] == ["LIVE"]
    assert set(cat) == {"LIVE"}


def test_no_metadata_survives_without_observations_and_no_weight_without_a_series() -> None:
    """The orphan invariant the database integrity checks assert in SQL."""
    observations = _series({"LIVE": [(LATEST, 100.0)], "DEAD": [(date(2025, 1, 1), 100.0)]})
    obs, weights, rows, cat, _ = apply_usable_series_filter(
        observations,
        {LATEST: {"LIVE": 1.0}},
        [{"series_id": "DEAD", "reference_date": LATEST, "weight": 1.0}],
        {"LIVE": {}, "DEAD": {}},
        latest_period=LATEST,
    )
    surviving = {sid for values in obs.values() for sid in values}
    assert set(cat) <= surviving
    assert {row["series_id"] for row in rows} <= surviving
    assert {sid for values in weights.values() for sid in values} <= surviving


def test_report_dropped_is_the_union_of_stale_and_empty() -> None:
    report = UsabilityReport(kept=("A",), stale=("B",), empty=("C",), protected_by_weight=())
    assert report.dropped == ("B", "C")
