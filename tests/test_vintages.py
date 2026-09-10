"""Same-day revisions update today's vintage; later revisions preserve history."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import text

from scripts.time_series import upsert_time_series
from scripts.weights import upsert_weights
from tests.test_idempotency import _engine


@pytest.mark.parametrize(
    ("table", "column", "upsert"),
    [
        ("time_series", "value", upsert_time_series),
        ("weights", "weight", upsert_weights),
    ],
)
def test_revision_history(tmp_path, table, column, upsert) -> None:
    engine = _engine(tmp_path)
    month = date(2026, 1, 1)
    first = datetime(2026, 8, 19)  # noqa: DTZ001
    later = datetime(2026, 8, 20)  # noqa: DTZ001
    assert upsert(engine, {month: {"S": 0.1}}, first) == (1, 0)
    assert upsert(engine, {month: {"S": 0.2}}, first) == (0, 0)
    assert upsert(engine, {month: {"S": 0.3}}, later) == (0, 1)
    assert upsert(engine, {month: {"S": 0.4}}, later) == (0, 0)
    assert upsert(engine, {month: {"S": 0.400000000001}}, later) == (0, 0)
    with engine.connect() as conn:
        assert conn.execute(
            text(f"SELECT {column} FROM collector_ons_cpi.{table} ORDER BY vintage_date")
        ).scalars().all() == [0.2, 0.4]
