"""Reconcile published UK CPI aggregates from their immediate COICOP children."""

from __future__ import annotations

import logging
from datetime import date
from itertools import pairwise
from typing import Any

from scripts.config import VALIDATION_TOLERANCE_PP
from scripts.extract import parse_series_id

logger = logging.getLogger(__name__)


def _parent_node(node: str) -> str | None:
    """Return the immediate parent token in the published COICOP hierarchy."""
    if node == "ALL":
        return None
    if node.startswith("D"):
        return "ALL"
    if node.startswith("G"):
        return f"D{node[1:3]}"
    if node.startswith("C"):
        return f"G{node[1:4]}"
    return None


def build_hierarchy(series_ids: list[str]) -> dict[str, list[str]]:
    """Build a reproducible parent-to-immediate-children map from series IDs."""
    by_node: dict[str, list[str]] = {}
    for series_id in series_ids:
        _, family, node, _, _ = parse_series_id(series_id)
        if family == "COICOP":
            by_node.setdefault(node, []).append(series_id)

    hierarchy: dict[str, list[str]] = {}
    for node, children_at_node in by_node.items():
        parent_node = _parent_node(node)
        if parent_node is None:
            continue
        parents = by_node.get(parent_node, [])
        if len(parents) != 1:
            logger.warning("Cannot resolve unique parent %s for node %s", parent_node, node)
            continue
        hierarchy.setdefault(parents[0], []).extend(children_at_node)
    return {parent: sorted(children) for parent, children in hierarchy.items()}


def validate_weight_sums(
    weights_by_date: dict[date, dict[str, float]],
    hierarchy: dict[str, list[str]],
    tolerance: float = 0.01,
) -> list[dict[str, Any]]:
    """Check that immediate child basket weights sum to each parent weight."""
    results: list[dict[str, Any]] = []
    for ref_date, weights in sorted(weights_by_date.items()):
        for parent, children in hierarchy.items():
            if parent not in weights or any(child not in weights for child in children):
                continue
            parent_weight = weights[parent]
            child_sum = sum(weights[child] for child in children)
            residual = child_sum - parent_weight
            results.append(
                {
                    "check": "weight_sum",
                    "reference_date": ref_date,
                    "parent_series_id": parent,
                    "published": parent_weight,
                    "reconstructed": child_sum,
                    "residual": residual,
                    "passed": abs(residual) <= tolerance,
                    "child_count": len(children),
                }
            )
    return results


def price_reference_month(ref_date: date) -> date:
    """Return the ONS price reference month backing the link ending in ``ref_date``.

    ONS aggregates with a Laspeyres-type index against an annual January price
    reference and chains the series in December, so February through December
    compare against January of the same year while January itself chains on the
    preceding December.
    """
    if ref_date.month == 1:
        return date(ref_date.year - 1, 12, 1)
    return date(ref_date.year, 1, 1)


def validate_bottom_up(
    observations: dict[date, dict[str, float | None]],
    weights_by_date: dict[date, dict[str, float]],
    hierarchy: dict[str, list[str]],
    tolerance_pp: float = VALIDATION_TOLERANCE_PP,
) -> list[dict[str, Any]]:
    """Reconstruct monthly parent inflation from price-updated child weights.

    Official basket weights remain untouched in storage. For each parent/month
    this check price-updates the immediate-child weights to the ONS price
    reference month, normalizes them locally, takes their weighted average price
    relative, and compares it with the published parent price relative:

        phi_i(t)   = w_i(t) * I_i(t-1)/I_i(ref) /
                     sum_j w_j(t) * I_j(t-1)/I_j(ref)
        R_hat(p,t) = sum_i phi_i(t) * I_i(t)/I_i(t-1)

    Omitting the ``I_i(ref)`` term is only valid when every child shares one
    January index level. Table 38 publishes 2015=100 levels that are never
    re-referenced to January, so dropping it biases the residual within the year.
    """
    dates = sorted(observations)
    results: list[dict[str, Any]] = []
    for previous_date, ref_date in pairwise(dates):
        if (ref_date.year * 12 + ref_date.month) - (
            previous_date.year * 12 + previous_date.month
        ) != 1:
            continue
        current = observations[ref_date]
        previous = observations[previous_date]
        weights = weights_by_date.get(ref_date)
        if not weights:
            continue
        reference_date = price_reference_month(ref_date)
        reference = observations.get(reference_date, {})
        for parent, children in hierarchy.items():
            parent_now = current.get(parent)
            parent_before = previous.get(parent)
            if parent_now is None or parent_before in (None, 0):
                continue
            usable = [
                child
                for child in children
                if child in weights
                and current.get(child) is not None
                and previous.get(child) not in (None, 0)
                and reference.get(child) not in (None, 0)
            ]
            if len(usable) != len(children):
                continue
            updated = {
                child: weights[child] * float(previous[child]) / float(reference[child])
                for child in usable
            }
            weight_total = sum(updated.values())
            if weight_total == 0:
                continue
            reconstructed_relative = (
                sum(
                    updated[child] * float(current[child]) / float(previous[child])
                    for child in usable
                )
                / weight_total
            )
            published_relative = float(parent_now) / float(parent_before)
            residual_pp = (reconstructed_relative - published_relative) * 100.0
            results.append(
                {
                    "check": "bottom_up_monthly_rate",
                    "reference_date": ref_date,
                    "price_reference_date": reference_date,
                    "parent_series_id": parent,
                    "published": (published_relative - 1.0) * 100.0,
                    "reconstructed": (reconstructed_relative - 1.0) * 100.0,
                    "residual": residual_pp,
                    "passed": abs(residual_pp) <= tolerance_pp,
                    "child_count": len(usable),
                }
            )
    return results


def log_validation_summary(results: list[dict[str, Any]], label: str) -> tuple[int, int, float]:
    """Log pass/fail counts and return ``(passed, failed, max_abs_residual)``."""
    passed = sum(bool(row["passed"]) for row in results)
    failed = len(results) - passed
    max_residual = max((abs(float(row["residual"])) for row in results), default=0.0)
    logger.info(
        "%s validation: checks=%d passed=%d failed=%d max_abs_residual=%.6f",
        label,
        len(results),
        passed,
        failed,
        max_residual,
    )
    if failed:
        worst = sorted(results, key=lambda row: abs(float(row["residual"])), reverse=True)[:10]
        for row in worst:
            if not row["passed"]:
                logger.warning(
                    "%s mismatch date=%s parent=%s residual=%.6f",
                    label,
                    row["reference_date"],
                    row["parent_series_id"],
                    row["residual"],
                )
    return passed, failed, max_residual
