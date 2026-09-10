"""Create an analyst-facing workbook mirroring indices, weights, and checks."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.extract import get_original_weight_catalog, get_series_catalog


def export_validation_xlsx(
    observations: dict[date, dict[str, float | None]],
    weights: dict[date, dict[str, float]],
    hierarchy: dict[str, list[str]],
    validation_rows: list[dict[str, Any]],
    output_path: Path,
    *,
    original_weights: dict[date, dict[str, float]] | None = None,
) -> Path:
    """Write the validation workbook and return its path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    index_frame = pd.DataFrame.from_dict(observations, orient="index").sort_index()
    weight_frame = pd.DataFrame.from_dict(weights, orient="index").sort_index()
    catalog = get_series_catalog()
    map_rows = [
        {
            "series_id": series_id,
            "family": fields["family"],
            "node": fields["node"],
            "native_id": fields["native_id"],
            "official_name": fields["name"],
            "parent_series_id": next(
                (parent for parent, children in hierarchy.items() if series_id in children), None
            ),
        }
        for series_id, fields in sorted(catalog.items())
    ]
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        index_frame.to_excel(writer, sheet_name="Time Series", index_label="reference_date")
        weight_frame.to_excel(writer, sheet_name="Weights", index_label="reference_date")
        if original_weights is not None:
            pd.DataFrame.from_dict(original_weights, orient="index").sort_index().to_excel(
                writer, sheet_name="Original Weights", index_label="reference_date"
            )
            pd.DataFrame.from_dict(get_original_weight_catalog(), orient="index").to_excel(
                writer, sheet_name="Original Weight Map", index_label="series_id"
            )
        pd.DataFrame(map_rows).to_excel(writer, sheet_name="Series Map", index=False)
        pd.DataFrame(validation_rows).to_excel(writer, sheet_name="Validation", index=False)
    return output_path
