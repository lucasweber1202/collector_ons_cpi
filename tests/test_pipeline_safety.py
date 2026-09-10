"""Validation is mandatory and failures must be logged without data writes."""

from __future__ import annotations

from collections import Counter
from datetime import date
from unittest.mock import Mock

import pytest

import main


def test_failure_is_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = Mock()
    log = Mock()
    monkeypatch.setattr(main, "build_engine", lambda: engine)
    monkeypatch.setattr(main, "init_db", lambda _: None)
    monkeypatch.setattr(main, "insert_run_log", log)
    monkeypatch.setattr(main, "main", Mock(side_effect=ValueError("source failure")))
    assert main.run(["--no-watch"]) == 1
    assert log.call_args.args[3] == "error"
    assert "source failure" in log.call_args.args[5]
    engine.dispose.assert_called_once()


def test_validation_cannot_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = Mock()
    write = Mock()
    monkeypatch.setattr(main, "_preflight", lambda: None)
    monkeypatch.setattr(main, "build_engine", lambda: engine)
    monkeypatch.setattr(main, "init_db", lambda _: None)
    monkeypatch.setattr(main, "get_max_reference_date", lambda _: None)
    monkeypatch.setattr(main, "collect_raw_data", lambda _: {date(2026, 1, 1): {}})
    monkeypatch.setattr(main, "collect_weights", lambda _: {})
    monkeypatch.setattr(main, "get_series_catalog", dict)
    monkeypatch.setattr(main, "validate_weight_sums", lambda *_: ([], Counter()))
    monkeypatch.setattr(main, "validate_bottom_up", lambda *_, **kw: ([], Counter()))
    monkeypatch.setattr(main, "upsert_time_series", write)
    with pytest.raises(ValueError, match="Validation failed"):
        main.main(main._parse_args(["--no-watch"]))
    write.assert_not_called()


def test_extraction_includes_december_for_january_chain() -> None:
    assert main._anchor_to_january(date(2026, 7, 1)) == date(2025, 12, 1)
