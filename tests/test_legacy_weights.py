"""Reject unsafe in-place conversion of existing official baskets."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from scripts import weights
from tests.test_idempotency import _engine


def test_legacy_storage_is_blocked(tmp_path) -> None:
    engine = _engine(tmp_path)
    weights.upsert_weights(
        engine,
        {date(2026, 1, 1): {"CPI_COICOP_ALL_AAAA_ALL_ITEMS": 1000}},
        datetime(2026, 8, 19),  # noqa: DTZ001
    )
    with pytest.raises(ValueError, match="legacy"):
        weights.assert_operational_storage(engine)
