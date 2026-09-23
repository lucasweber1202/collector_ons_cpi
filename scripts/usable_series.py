"""GUIDELINES 5.1 usable-series filtering for the CPI target.

The rule is that a series with no recent update, or with no usable history,
must not reach persistence. Applying it to a forecast target needs more care
than applying it to a predictor, because here the series *are* the target: a
series dropped in error does not merely cost a feature, it silently corrupts
the basket and the aggregates rebuilt from it.

Two properties keep that from happening.

**Staleness is the only drop signal.** No minimum-history threshold is applied.
Measured against the live basket, 681 of 860 series begin partway through the
collected window -- the consumption-segment layer starts in February 2025, and
COICOP classes are routinely born by rebasing and reclassification. A
minimum-history rule worth having would delete most of the basket. Staleness
separates cleanly instead: 844 series print in the latest month and exactly 16
stop 6.9 months earlier, those being consumption segments ONS retired from
later editions.

**A weighted series is never dropped.** Whatever its staleness, a series
carrying a weight in the current regime is load-bearing for reconstruction, so
it is kept. This is what makes the filter structurally unable to break the
basket: to be dropped, a series must be both stale *and* absent from the
current weight regime, and the published basket never leaves a live component
unweighted.

Filtering runs after validation and before the transaction. Validation
therefore still scores the complete published basket, so the filter cannot
mask a reconciliation failure by removing the series that caused it.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from scripts.config import MAX_STALE_MONTHS

logger = logging.getLogger(__name__)

Observations = dict[date, dict[str, float | None]]
Weights = dict[date, dict[str, float]]


@dataclass(frozen=True)
class UsabilityReport:
    """Which series survived 5.1, and why the others did not."""

    kept: tuple[str, ...]
    stale: tuple[str, ...]
    empty: tuple[str, ...]
    protected_by_weight: tuple[str, ...]

    @property
    def dropped(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.stale) | set(self.empty)))


def _month_distance(later: date, earlier: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def _last_non_null(observations: Observations, series_id: str) -> date | None:
    months = [month for month, values in observations.items() if values.get(series_id) is not None]
    return max(months) if months else None


def _weighted_in_current_regime(weights: Weights, series_id: str) -> bool:
    if not weights:
        return False
    current = max(weights)
    return series_id in weights[current]


def classify_series(
    observations: Observations,
    weights: Weights,
    *,
    latest_period: date,
    max_stale_months: int = MAX_STALE_MONTHS,
) -> UsabilityReport:
    """Decide, per series_id, whether 5.1 admits it to persistence."""
    series_ids = {series_id for values in observations.values() for series_id in values}
    kept: list[str] = []
    stale: list[str] = []
    empty: list[str] = []
    protected: list[str] = []
    for series_id in sorted(series_ids):
        last_seen = _last_non_null(observations, series_id)
        weighted = _weighted_in_current_regime(weights, series_id)
        if weighted:
            # Load-bearing for reconstruction: kept regardless of staleness.
            kept.append(series_id)
            if last_seen is None or _month_distance(latest_period, last_seen) > max_stale_months:
                protected.append(series_id)
            continue
        if last_seen is None:
            empty.append(series_id)
            continue
        if _month_distance(latest_period, last_seen) > max_stale_months:
            stale.append(series_id)
            continue
        kept.append(series_id)
    return UsabilityReport(
        kept=tuple(kept),
        stale=tuple(stale),
        empty=tuple(empty),
        protected_by_weight=tuple(protected),
    )


# Every pruner below removes the series the filter *judged* unusable, rather
# than retaining only those it judged usable. The distinction is not cosmetic.
# 5.1 classifies series from the observation set, but the published basket
# carries official weights for series that have no observation in the
# collected window -- 156 of them on the live basket. Keeping only the
# classified set would delete those as collateral, which is the exact failure
# 5.1 exists to prevent. Anything the filter did not classify is left alone.


def _drop_observations(observations: Observations, drop: set[str]) -> Observations:
    filtered: Observations = {}
    for month, values in observations.items():
        retained = {sid: value for sid, value in values.items() if sid not in drop}
        if retained:
            filtered[month] = retained
    return filtered


def _drop_weights(weights: Weights, drop: set[str]) -> Weights:
    filtered: Weights = {}
    for month, values in weights.items():
        retained = {sid: value for sid, value in values.items() if sid not in drop}
        if retained:
            filtered[month] = retained
    return filtered


def _drop_weight_rows(rows: list[dict[str, Any]], drop: set[str]) -> list[dict[str, Any]]:
    return [row for row in rows if row["series_id"] not in drop]


def _drop_from_catalog(
    catalog: Mapping[str, dict[str, str]], drop: set[str]
) -> dict[str, dict[str, str]]:
    return {sid: fields for sid, fields in catalog.items() if sid not in drop}


def apply_usable_series_filter(
    observations: Observations,
    operational: Weights,
    original_weight_rows: list[dict[str, Any]],
    catalog: Mapping[str, dict[str, str]],
    *,
    latest_period: date,
    max_stale_months: int = MAX_STALE_MONTHS,
) -> tuple[Observations, Weights, list[dict[str, Any]], dict[str, dict[str, str]], UsabilityReport]:
    """Prune unusable series from everything that is about to be written.

    Every persisted layer is pruned with the same key set, so a dropped series
    cannot leave metadata without observations, or a weight without a series.
    """
    report = classify_series(
        observations, operational, latest_period=latest_period, max_stale_months=max_stale_months
    )
    drop = set(report.dropped)
    logger.info(
        "Usable-series filter: kept %d, dropped %d (stale=%d empty=%d; "
        "max_stale_months=%d, latest_period=%s)",
        len(report.kept),
        len(report.dropped),
        len(report.stale),
        len(report.empty),
        max_stale_months,
        latest_period,
    )
    if report.protected_by_weight:
        logger.info(
            "Usable-series filter: %d stale series kept because they carry a weight in the "
            "current regime and are load-bearing for reconstruction",
            len(report.protected_by_weight),
        )
    if report.dropped:
        logger.info("Usable-series filter dropped: %s", ", ".join(report.dropped))
    return (
        _drop_observations(observations, drop),
        _drop_weights(operational, drop),
        _drop_weight_rows(original_weight_rows, drop),
        _drop_from_catalog(catalog, drop),
        report,
    )
