"""ONS UK CPI collector with basket weights and hierarchy-aware reconciliation."""

from __future__ import annotations

import argparse
import io
import logging
import sys
import time
import traceback
from datetime import UTC, date, datetime
from pathlib import Path

from scripts.config import (
    DEFAULT_START_DATE,
    LOG_LEVEL,
    MAX_WAIT,
    POLL_INTERVAL,
    ROOT_DIR,
    START_DATE_LOOKBACK_MONTHS,
)
from scripts.db import build_engine
from scripts.export_validation_xlsx import export_validation_xlsx
from scripts.extract import collect_raw_data, collect_weights, get_series_catalog
from scripts.init_db import init_db
from scripts.metadata import upsert_metadata
from scripts.run_logs import insert_run_log
from scripts.time_series import get_max_reference_date, upsert_time_series
from scripts.validate import (
    build_hierarchy,
    log_validation_summary,
    validate_bottom_up,
    validate_weight_sums,
)
from scripts.weights import upsert_weights

logger = logging.getLogger("main")


def _setup_logging(level: str) -> io.StringIO:
    """Capture collector logs while suppressing noisy third-party INFO output."""
    buffer = io.StringIO()
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setFormatter(formatter)
    buffer_handler = logging.StreamHandler(stream=buffer)
    buffer_handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.ERROR)
    root.addHandler(stream_handler)
    root.addHandler(buffer_handler)
    app_level = level.upper()
    logging.getLogger("main").setLevel(app_level)
    logging.getLogger("scripts").setLevel(app_level)
    return buffer


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect official ONS UK CPI indices, basket weights, and bottom-up checks."
    )
    parser.add_argument("--log-level", default=LOG_LEVEL)
    parser.add_argument("--start-date", type=date.fromisoformat, default=None)
    parser.add_argument(
        "--no-watch",
        action="store_true",
        help="Run once without waiting for the next monthly release.",
    )
    parser.add_argument(
        "--strict-validation",
        action="store_true",
        help="Fail when any configured bottom-up tolerance is exceeded.",
    )
    parser.add_argument(
        "--export-validation",
        action="store_true",
        help="Write _verify_xls/ons_cpi_validation.xlsx.",
    )
    return parser.parse_args(argv)


def _shift_months(value: date, months: int) -> date:
    """Shift a first-of-month date without an extra date dependency."""
    ordinal = value.year * 12 + value.month - 1 + months
    return date(ordinal // 12, ordinal % 12 + 1, 1)


def _wait_for_release(latest: date) -> tuple[dict[date, dict[str, float | None]], date] | None:
    """Poll until the month after ``latest`` appears or timeout expires."""
    expected = _shift_months(latest.replace(day=1), 1)
    validation_start = _shift_months(expected, -1)
    deadline = time.monotonic() + MAX_WAIT
    while True:
        parsed = collect_raw_data(validation_start)
        if parsed and max(parsed) >= expected:
            logger.info("Detected ONS CPI release for %s", expected)
            return parsed, validation_start
        if time.monotonic() >= deadline:
            logger.info("No CPI release for %s before timeout; exiting normally", expected)
            return None
        remaining = max(0.0, deadline - time.monotonic())
        delay = min(POLL_INTERVAL, remaining)
        logger.info("CPI %s not available; checking again in %.0fs", expected, delay)
        time.sleep(delay)


def _rewind_start(latest: date) -> date:
    """Return the standard revision lookback month."""
    return _shift_months(latest.replace(day=1), -START_DATE_LOOKBACK_MONTHS)


def main(args: argparse.Namespace) -> int:
    """Run extraction, validation, weights, time series, then metadata."""
    logger.info("Starting ONS UK CPI collector")
    engine = build_engine()
    init_db(engine)
    latest = get_max_reference_date(engine)

    if args.start_date is not None:
        extraction_start = args.start_date.replace(day=1)
        parsed = collect_raw_data(extraction_start)
    elif latest is None:
        extraction_start = DEFAULT_START_DATE
        parsed = collect_raw_data(extraction_start)
    elif args.no_watch:
        extraction_start = _rewind_start(latest)
        parsed = collect_raw_data(extraction_start)
    else:
        release = _wait_for_release(latest)
        if release is None:
            return 0
        parsed, extraction_start = release

    weights = collect_weights(max(extraction_start, date(2008, 1, 1)))
    hierarchy = build_hierarchy(list(get_series_catalog()))
    weight_checks = validate_weight_sums(weights, hierarchy)
    bottom_up_checks = validate_bottom_up(parsed, weights, hierarchy)
    _, failed_weights, _ = log_validation_summary(weight_checks, "Basket-weight")
    _, failed_bottom_up, _ = log_validation_summary(bottom_up_checks, "Bottom-up")
    if args.strict_validation and (failed_weights or failed_bottom_up):
        raise ValueError(
            f"Validation failed: weight_checks={failed_weights}, bottom_up_checks={failed_bottom_up}"
        )

    collected_at = datetime.now(UTC)
    new_obs, new_vintages = upsert_time_series(engine, parsed, collected_at)
    new_weights, weight_vintages = upsert_weights(engine, weights, collected_at)
    metadata_inserted, metadata_updated = upsert_metadata(engine, parsed, collected_at)
    logger.info(
        "Run result: observations=%d vintages=%d weights=%d weight_vintages=%d "
        "metadata_inserted=%d metadata_updated=%d",
        new_obs,
        new_vintages,
        new_weights,
        weight_vintages,
        metadata_inserted,
        metadata_updated,
    )
    if args.export_validation:
        output = export_validation_xlsx(
            parsed,
            weights,
            hierarchy,
            weight_checks + bottom_up_checks,
            Path(ROOT_DIR) / "_verify_xls" / "ons_cpi_validation.xlsx",
        )
        logger.info("Wrote validation workbook to %s", output)
    return 0


if __name__ == "__main__":
    arguments = _parse_args(sys.argv[1:])
    log_buffer = _setup_logging(arguments.log_level)
    started_at = datetime.now(UTC)
    status = "success"
    traceback_text: str | None = None
    return_code = 0
    try:
        return_code = main(arguments)
    except Exception:
        status = "error"
        traceback_text = traceback.format_exc()
        logger.exception("Pipeline failed")
        return_code = 1
    finally:
        finished_at = datetime.now(UTC)
        try:
            log_engine = build_engine()
            init_db(log_engine)
            insert_run_log(
                log_engine,
                started_at,
                finished_at,
                status,
                log_buffer.getvalue(),
                traceback_text,
            )
        except Exception:
            logger.exception("Could not persist run log")
    if return_code != 0:
        raise SystemExit(return_code)
