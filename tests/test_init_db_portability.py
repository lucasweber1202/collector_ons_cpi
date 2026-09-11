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


# Constructs that exist in PostgreSQL but not in Databricks SQL, or that mean
# different things in the two engines. Every statement the collector emits must
# stay inside the documented common subset.
POSTGRES_ONLY = (
    "SERIAL",
    "JSONB",
    "ON CONFLICT",
    "RETURNING",
    "ILIKE",
    "DISTINCT ON",
    " FILTER (",
    "::",
    "DOUBLE PRECISION",
    "TEXT ",
    "TIMESTAMPTZ",
    "NOW()",
    "CURRENT_TIMESTAMP",
)


def _statements() -> list[str]:
    """Render every statement the collector sends, as it is sent."""
    from scripts import metadata, original_weights, time_series, weights

    rendered = [
        str(time_series._insert_statement(2)),
        str(time_series._merge_statement(2)),
        str(time_series._UPDATE_SQL),
        str(weights._insert_statement(2)),
        str(weights._merge_statement(2)),
        str(weights._UPDATE_SQL),
        str(original_weights._insert_statement(2)),
        str(original_weights._merge_statement(2)),
        str(original_weights._UPDATE_SQL),
        str(metadata._insert_statement(2)),
        str(metadata._merge_statement(2)),
        str(metadata._UPDATE_SQL),
    ]
    return rendered


@pytest.mark.parametrize("statement", _statements())
def test_emitted_sql_stays_in_the_portable_subset(statement: str) -> None:
    upper = statement.upper()
    for construct in POSTGRES_ONLY:
        assert construct not in upper, f"{construct} is not portable: {statement}"


@pytest.mark.parametrize("statement", _statements())
def test_emitted_sql_only_interpolates_trusted_identifiers(statement: str) -> None:
    """Every value travels as a named parameter; only constants are inlined."""
    from scripts.config import SCHEMA_NAME

    assert SCHEMA_NAME in statement
    assert "'" not in statement


def test_merge_matches_on_the_full_natural_key() -> None:
    """Databricks treats primary keys as informational, so the ON clause is the key."""
    from scripts import original_weights, time_series, weights

    for module in (time_series, weights, original_weights):
        condition = str(module._merge_statement(1)).split(" ON ", 1)[1]
        for column in module._KEY_COLUMNS:
            assert f"target.{column} = source.{column}" in condition
