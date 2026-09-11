"""Reviewed ONS MM23 crosswalk for CPI exclusion/special aggregates.

This module deliberately does not persist MM23 weights yet. The source publishes
those weights as annual observations while this collector's existing
``original_weights`` contract is reference-month based. Until that storage
semantics is explicitly resolved, this file is a source-verified identity map
and a resolver for Table 38 ``ALT`` series only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict

MM23_DATASET_URL = (
    "https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceindices"
)


class SpecialAggregate(TypedDict):
    """Native ONS identifiers that describe one CPI exclusion aggregate."""

    label: str
    weight_cdid: str
    index_cdid: str
    rate_12m_cdid: str
    complement_weight_cdid: str
    complement_index_cdid: str
    complement_rate_12m_cdid: str


# Every row below is linked by ONS on the MM23 time-series pages. The complement
# is the published component removed from the exclusion index. Its annual weight
# plus the exclusion weight equals 1,000 parts per 1,000 in the same MM23 year.
EX_CPI_SPECIAL_AGGREGATES: tuple[SpecialAggregate, ...] = (
    {
        "label": "CPI excluding tobacco",
        "weight_cdid": "A9F5",
        "index_cdid": "DK9V",
        "rate_12m_cdid": "DKL7",
        "complement_weight_cdid": "CJWP",
        "complement_index_cdid": "D7CB",
        "complement_rate_12m_cdid": "D7GN",
    },
    {
        "label": "CPI excluding energy",
        "weight_cdid": "A9FT",
        "index_cdid": "DKC5",
        "rate_12m_cdid": "DKO7",
        "complement_weight_cdid": "A9F3",
        "complement_index_cdid": "DK9T",
        "complement_rate_12m_cdid": "DKL5",
    },
    {
        "label": "CPI excluding energy, food, alcohol and tobacco",
        "weight_cdid": "A9FU",
        "index_cdid": "DKC6",
        "rate_12m_cdid": "DKO8",
        "complement_weight_cdid": "A9G4",
        "complement_index_cdid": "DKD6",
        "complement_rate_12m_cdid": "DKP8",
    },
    {
        "label": "CPI excluding energy and unprocessed food",
        "weight_cdid": "A9FV",
        "index_cdid": "DKC7",
        "rate_12m_cdid": "DKO9",
        "complement_weight_cdid": "A9G5",
        "complement_index_cdid": "DKD7",
        "complement_rate_12m_cdid": "DKP9",
    },
    {
        "label": "CPI excluding seasonal food",
        "weight_cdid": "A9FW",
        "index_cdid": "DKC8",
        "rate_12m_cdid": "DKP2",
        "complement_weight_cdid": "A9EZ",
        "complement_index_cdid": "DK9R",
        "complement_rate_12m_cdid": "DKL3",
    },
    {
        "label": "CPI excluding energy and seasonal food",
        "weight_cdid": "A9FX",
        "index_cdid": "DKC9",
        "rate_12m_cdid": "DKP3",
        "complement_weight_cdid": "A9G6",
        "complement_index_cdid": "DKD8",
        "complement_rate_12m_cdid": "DKQ2",
    },
    {
        "label": "CPI excluding alcohol and tobacco",
        "weight_cdid": "A9FY",
        "index_cdid": "DKD2",
        "rate_12m_cdid": "DKP4",
        "complement_weight_cdid": "CHZS",
        "complement_index_cdid": "D7BV",
        "complement_rate_12m_cdid": "D7G9",
    },
    {
        "label": "CPI excluding liquid fuels, vehicle fuels and lubricants",
        "weight_cdid": "A9FZ",
        "index_cdid": "DKD3",
        "rate_12m_cdid": "DKP5",
        "complement_weight_cdid": "A9FS",
        "complement_index_cdid": "DKC4",
        "complement_rate_12m_cdid": "DKO6",
    },
    {
        "label": "CPI excluding housing, water, electricity, gas and other fuels",
        "weight_cdid": "A9G2",
        "index_cdid": "DKD4",
        "rate_12m_cdid": "DKP6",
        "complement_weight_cdid": "CHZU",
        "complement_index_cdid": "D7BX",
        "complement_rate_12m_cdid": "D7GB",
    },
    {
        "label": "CPI excluding education, health and social protection",
        "weight_cdid": "A9G3",
        "index_cdid": "DKD5",
        "rate_12m_cdid": "DKP7",
        "complement_weight_cdid": "A9G7",
        "complement_index_cdid": "DKD9",
        "complement_rate_12m_cdid": "DKQ3",
    },
)


def validate_crosswalk() -> None:
    """Fail if a reviewed native identifier is accidentally duplicated."""
    fields = (
        "weight_cdid",
        "index_cdid",
        "rate_12m_cdid",
        "complement_weight_cdid",
        "complement_index_cdid",
        "complement_rate_12m_cdid",
    )
    for field in fields:
        values = [row[field] for row in EX_CPI_SPECIAL_AGGREGATES]
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate MM23 {field} in ex-CPI crosswalk")
    for row in EX_CPI_SPECIAL_AGGREGATES:
        if row["weight_cdid"] == row["complement_weight_cdid"]:
            raise ValueError(f"Exclusion and complement weights collide: {row['label']}")


def resolve_table38_alt_series(
    catalog: Mapping[str, Mapping[str, str]],
) -> tuple[dict[str, str], list[str]]:
    """Resolve reviewed MM23 index CDIDs onto already-collected Table 38 ALT IDs.

    Returns ``(resolved, missing)`` where ``resolved`` maps the MM23 index CDID
    to this collector's stable ``series_id``. Resolution is exact on the native
    ONS CDID and only accepts the ``ALT`` family; no name/fuzzy fallback exists.
    Missing rows are reported rather than fabricated so the caller can decide
    whether a source release changed scope.
    """
    by_native: dict[str, list[str]] = {}
    for series_id, fields in catalog.items():
        if fields.get("family") != "ALT":
            continue
        native_id = str(fields.get("native_id", "")).upper()
        if native_id:
            by_native.setdefault(native_id, []).append(series_id)

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for row in EX_CPI_SPECIAL_AGGREGATES:
        native_id = row["index_cdid"]
        candidates = by_native.get(native_id, [])
        if len(candidates) > 1:
            raise ValueError(f"Table 38 publishes duplicate ALT CDID {native_id}: {candidates}")
        if not candidates:
            missing.append(native_id)
            continue
        resolved[native_id] = candidates[0]
    return resolved, missing


validate_crosswalk()
