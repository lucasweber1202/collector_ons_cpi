"""The review workbook must distinguish transformed and source weights."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from scripts.export_validation_xlsx import export_validation_xlsx


def test_export_has_original_weights(tmp_path: Path) -> None:
    month = date(2026, 2, 1)
    output = export_validation_xlsx(
        {month: {"index": 100.0}},
        {month: {"index": 1.0}},
        {},
        [],
        tmp_path / "review.xlsx",
        original_weights={month: {"CPI_W1_0": 1000.0}},
    )
    with pd.ExcelFile(output) as workbook:
        assert {"Time Series", "Weights", "Original Weights", "Series Map", "Validation"} <= set(
            workbook.sheet_names
        )
        assert pd.read_excel(workbook, "Original Weights").iloc[0, 1] == 1000.0
