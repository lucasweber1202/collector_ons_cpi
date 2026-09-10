"""Official basket regimes and revision vintages remain separate."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from sqlalchemy import text

from scripts import init_db, original_weights
from tests.test_idempotency import _engine


def test_original_regimes_and_revisions(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        conn.execute(text(init_db.CREATE_ORIGINAL_WEIGHTS_TABLE.format(double="DOUBLE")))
    jan, feb = date(2026, 1, 1), date(2026, 2, 1)
    first = datetime(2026, 8, 19)  # noqa: DTZ001
    later = datetime(2026, 8, 20)  # noqa: DTZ001
    values = {jan: {"CPI_W1_0": 1000}, feb: {"CPI_W1_0": 999}}
    assert original_weights.upsert_original_weights(engine, values, first) == (2, 0)
    assert original_weights.upsert_original_weights(engine, values, first) == (0, 0)
    values[feb]["CPI_W1_0"] = 998
    assert original_weights.upsert_original_weights(engine, values, first) == (0, 0)
    values[feb]["CPI_W1_0"] = 997
    assert original_weights.upsert_original_weights(engine, values, later) == (0, 1)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT weight, weight_base_year FROM collector_ons_cpi.original_weights "
                "ORDER BY reference_date, vintage_date"
            )
        ).all()
    assert rows == [(1000, 2026), (998, 2026), (997, 2026)]
