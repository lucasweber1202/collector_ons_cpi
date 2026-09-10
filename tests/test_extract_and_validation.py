"""Focused regression tests for structured IDs, hierarchy, and CPI reconciliation."""

from __future__ import annotations

from collections import Counter
from datetime import date

import pytest

from scripts.extract import _make_series_id, _node_token, _weight_header, parse_series_id
from scripts.validate import build_hierarchy, validate_bottom_up, validate_weight_sums


def _sid(node: str, native: str, name: str) -> str:
    family = "COICOP"
    return _make_series_id(family, node, native, name)


def test_series_id_round_trip_and_node_normalization() -> None:
    series_id = _sid("D01", "D7BU", "Food and non-alcoholic beverages")
    assert parse_series_id(series_id) == (
        "CPI",
        "COICOP",
        "D01",
        "D7BU",
        "FOOD_AND_NON_ALCOHOLIC_BEVERAGES",
    )
    assert _node_token("01.1") == ("COICOP", "G011")
    assert _node_token("Agg2") == ("ALT", "A02")


def test_weight_header_preserves_double_weight_regimes() -> None:
    assert _weight_header("2026 Jan") == (2026, (1,))
    assert _weight_header("2026 Feb-Dec") == (2026, tuple(range(2, 13)))
    assert _weight_header(2016) == (2016, tuple(range(1, 13)))


def test_hierarchy_and_bottom_up_exact_case() -> None:
    all_items = _sid("ALL", "A", "All items")
    first = _sid("D01", "B", "First division")
    second = _sid("D02", "C", "Second division")
    hierarchy = build_hierarchy([all_items, first, second])
    assert hierarchy == {all_items: sorted([first, second])}
    observations = {
        date(2026, 1, 1): {all_items: 100.0, first: 100.0, second: 100.0},
        date(2026, 2, 1): {all_items: 102.5, first: 110.0, second: 100.0},
    }
    weights = {date(2026, 2, 1): {all_items: 1000.0, first: 250.0, second: 750.0}}
    weight_results, weight_skips = validate_weight_sums(weights, hierarchy)
    bottom_results, bottom_skips = validate_bottom_up(
        observations, weights, hierarchy, tolerance_pp=1e-12
    )
    assert weight_results[0]["passed"] is True
    assert bottom_results[0]["passed"] is True
    assert bottom_results[0]["residual"] == pytest.approx(0.0, abs=1e-12)
    assert weight_skips == Counter()
    assert bottom_skips == Counter()


def test_bottom_up_flags_material_mismatch() -> None:
    all_items = _sid("ALL", "A", "All items")
    first = _sid("D01", "B", "First division")
    second = _sid("D02", "C", "Second division")
    observations = {
        date(2026, 1, 1): {all_items: 100.0, first: 100.0, second: 100.0},
        date(2026, 2, 1): {all_items: 110.0, first: 100.0, second: 100.0},
    }
    weights = {date(2026, 2, 1): {all_items: 1000.0, first: 500.0, second: 500.0}}
    results, _ = validate_bottom_up(
        observations, weights, build_hierarchy([all_items, first, second]), tolerance_pp=0.1
    )
    result = results[0]
    assert result["passed"] is False
    assert result["residual"] == pytest.approx(-10.0)
