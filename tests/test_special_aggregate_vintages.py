"""Tests for MM23 archived snapshot discovery and January-regime selection."""

from __future__ import annotations

from datetime import datetime

import pytest

from scripts.special_aggregate_vintages import (
    january_regime_snapshots,
    parse_mm23_snapshot_index,
)


def _row(version: str, reason: str, superseded: str) -> str:
    href = (
        "/file?uri=%2Feconomy%2Finflationandpriceindices%2Fdatasets%2F"
        "consumerpriceindices%2Fcurrent%2Fprevious%2F"
        f"{version}%2Fmm23.csv"
    )
    return (
        "<tr>"
        f'<td><a href="{href}">csv</a></td>'
        f"<td>{reason}</td>"
        f"<td>{superseded}</td>"
        "</tr>"
    )


def _page(*rows: str) -> str:
    return "<table>" + "".join(rows) + "</table>"


def test_snapshot_index_parses_version_url_date_and_reason() -> None:
    page = _page(_row("v130", "Scheduled update/revision", "25 March 2026 07:00"))

    snapshots = parse_mm23_snapshot_index(page)

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.version_id == "v130"
    assert snapshot.superseded_at == datetime(2026, 3, 25, 7, 0)
    assert snapshot.reason == "scheduled"
    assert "previous%2Fv130%2Fmm23.csv" in snapshot.csv_url


def test_january_regime_uses_scheduled_march_snapshot_not_same_day_correction() -> None:
    page = _page(
        _row("v118", "Scheduled update/revision", "26 March 2025 07:00"),
        _row("v130", "Scheduled update/revision", "25 March 2026 07:00"),
        _row("v131", "Correction See correction", "25 March 2026 12:51"),
    )

    selected = january_regime_snapshots(parse_mm23_snapshot_index(page))

    assert selected[2025].version_id == "v118"
    assert selected[2026].version_id == "v130"
    assert all(snapshot.reason == "scheduled" for snapshot in selected.values())


def test_january_regime_ignores_pre_double_update_years() -> None:
    page = _page(
        _row("v1", "Scheduled update/revision", "23 March 2016 07:00"),
        _row("v2", "Scheduled update/revision", "21 March 2017 07:00"),
    )

    selected = january_regime_snapshots(parse_mm23_snapshot_index(page))

    assert set(selected) == {2017}


def test_january_regime_rejects_two_scheduled_march_snapshots_for_one_year() -> None:
    page = _page(
        _row("v130", "Scheduled update/revision", "25 March 2026 07:00"),
        _row("v131", "Scheduled update/revision", "25 March 2026 12:51"),
    )

    with pytest.raises(ValueError, match="Two scheduled March MM23 snapshots found for 2026"):
        january_regime_snapshots(parse_mm23_snapshot_index(page))


def test_snapshot_index_fails_loudly_when_layout_has_no_versioned_csv() -> None:
    page = _page("<tr><td>No archived files</td><td>25 March 2026 07:00</td></tr>")

    with pytest.raises(ValueError, match="no versioned CSV snapshots"):
        parse_mm23_snapshot_index(page)
