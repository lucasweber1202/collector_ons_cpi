"""Regression tests for the dialect-dependent 64-bit float spelling in the DDL.

PostgreSQL and Databricks SQL share no spelling for a 64-bit float, and the one
spelling both accept, FLOAT, means 8 bytes on PostgreSQL and 4 on Databricks.
These tests pin the mapping so a future edit cannot silently halve precision.
"""

from __future__ import annotations

import pytest

from scripts.init_db import CREATE_TIME_SERIES_TABLE, CREATE_WEIGHTS_TABLE, double_type


def test_postgresql_uses_double_precision() -> None:
    """PostgreSQL has no DOUBLE type; the ANSI spelling is required."""
    assert double_type("postgresql") == "DOUBLE PRECISION"


def test_databricks_uses_double() -> None:
    """Spark lists DOUBLE as the only alias for DoubleType."""
    assert double_type("databricks") == "DOUBLE"


def test_unknown_dialect_falls_back_to_double() -> None:
    assert double_type("sqlite") == "DOUBLE"


@pytest.mark.parametrize("template", [CREATE_TIME_SERIES_TABLE, CREATE_WEIGHTS_TABLE])
def test_float_is_never_emitted(template: str) -> None:
    """FLOAT would be accepted by both engines at different precisions."""
    for dialect in ("postgresql", "databricks", "sqlite"):
        rendered = template.format(double=double_type(dialect))
        assert " FLOAT" not in rendered.upper()
        assert " REAL" not in rendered.upper()
