"""The ten CPI exclusion aggregates belong to collector_ons_ex_cpi, not here.

Table 38 publishes them alongside the aggregates this collector owns, so the
split is enforced on the stable ONS CDID rather than on a title. These tests
pin both halves of that contract: the ten are never collected here, and every
other analytical aggregate still is.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from scripts import extract
from tests.conftest import default_table38_series

# The reviewed hand-off, spelled out independently of the production constant so
# that editing the constant cannot quietly edit the test that guards it.
EXCLUSION_CDIDS = (
    "DK9V",
    "DKC5",
    "DKC6",
    "DKC7",
    "DKC8",
    "DKC9",
    "DKD2",
    "DKD3",
    "DKD4",
    "DKD5",
)


def _with_exclusion_aggregates(*, drop: str | None = None) -> list[tuple[str, str, str]]:
    """Table 38 as ONS publishes it: owned aggregates plus the exclusion ones."""
    series = default_table38_series()
    series += [
        (f"Agg{40 + index}", cdid, f"CPI excluding thing {index}")
        for index, cdid in enumerate(EXCLUSION_CDIDS)
        if cdid != drop
    ]
    return series


def test_the_reviewed_set_is_exactly_the_ten_ex_cpi_cdids() -> None:
    assert extract.EXCLUSION_AGGREGATE_CDIDS == frozenset(EXCLUSION_CDIDS)


def test_exclusion_aggregates_are_not_collected(
    cpi_workbook: Callable[..., bytes],
) -> None:
    """None of the ten reaches the catalog, the observations or an identifier."""
    parsed = extract.parse_cpi_workbook(cpi_workbook(_with_exclusion_aggregates()))
    catalog = extract.get_series_catalog()
    collected_cdids = {fields["native_id"] for fields in catalog.values()}

    assert collected_cdids.isdisjoint(EXCLUSION_CDIDS)
    for values in parsed.values():
        for series_id in values:
            assert extract.parse_series_id(series_id)[3] not in EXCLUSION_CDIDS


def test_other_analytical_aggregates_are_preserved(
    cpi_workbook: Callable[..., bytes],
) -> None:
    """Excluding the ten must not cost this collector its own ALT series."""
    extract.parse_cpi_workbook(cpi_workbook(_with_exclusion_aggregates()))
    catalog = extract.get_series_catalog()

    assert catalog["CPI_ALT_A02_D7F4"]["name"] == "All Goods"
    assert catalog["CPI_ALT_A20_D7F5"]["name"] == "All Services"
    assert {"D7BT", "D7BU", "D7C8", "D7D5", "D7C2", "D7C7"} <= {
        fields["native_id"] for fields in catalog.values()
    }


def test_a_partially_withdrawn_exclusion_set_stops_the_run(
    cpi_workbook: Callable[..., bytes],
) -> None:
    """Nine of ten means ONS moved one; the split must be re-reviewed, not guessed."""
    series = _with_exclusion_aggregates(drop="DKC5")
    with pytest.raises(ValueError, match=r"only part of the exclusion aggregates"):
        extract.parse_cpi_workbook(cpi_workbook(series))


def test_a_sheet_without_the_product_is_not_treated_as_drift(
    cpi_workbook: Callable[..., bytes],
) -> None:
    """A Table 38 that publishes none of the ten is not a partial withdrawal."""
    parsed = extract.parse_cpi_workbook(cpi_workbook(default_table38_series()))
    assert parsed
