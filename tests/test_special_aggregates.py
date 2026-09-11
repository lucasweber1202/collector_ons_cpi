"""Tests for the reviewed MM23 ex-CPI identity map."""

from __future__ import annotations

import pytest

from scripts.special_aggregates import (
    EX_CPI_SPECIAL_AGGREGATES,
    resolve_table38_alt_series,
    validate_crosswalk,
)


def test_crosswalk_is_reviewed_and_unique() -> None:
    validate_crosswalk()
    assert len(EX_CPI_SPECIAL_AGGREGATES) == 10
    assert {row["index_cdid"] for row in EX_CPI_SPECIAL_AGGREGATES} == {
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
    }


def test_resolver_matches_alt_by_native_cdid_only() -> None:
    catalog = {
        "CPI_ALT_A01_DKC6": {"family": "ALT", "native_id": "DKC6"},
        "CPI_ALT_A02_DKC5": {"family": "ALT", "native_id": "DKC5"},
        # A COICOP row with a target CDID must not be accepted as an ALT match.
        "CPI_COICOP_C0000_DK9V": {"family": "COICOP", "native_id": "DK9V"},
    }

    resolved, missing = resolve_table38_alt_series(catalog)

    assert resolved == {
        "DKC5": "CPI_ALT_A02_DKC5",
        "DKC6": "CPI_ALT_A01_DKC6",
    }
    assert "DK9V" in missing
    assert len(missing) == 8


def test_resolver_rejects_duplicate_alt_cdid() -> None:
    catalog = {
        "CPI_ALT_A01_DKC6": {"family": "ALT", "native_id": "DKC6"},
        "CPI_ALT_A99_DKC6": {"family": "ALT", "native_id": "DKC6"},
    }

    with pytest.raises(ValueError, match="duplicate ALT CDID DKC6"):
        resolve_table38_alt_series(catalog)
