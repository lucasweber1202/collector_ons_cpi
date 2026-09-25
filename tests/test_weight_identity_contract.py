"""The identity contract for official weights, and the crosswalk that proves it.

Table 38 indexes COICOP down to class level. The W1 workbook publishes weights
below that level and for analytical totals the index set does not carry, so
`original_weights` legitimately holds more distinct identities than `metadata`.
That is the source's shape: a published weight is part of the official record
and is stored unmodified under the identity the workbook gives it, rather than
being dropped, renamed onto a parent, or normalised away.

The contract is therefore not "every weight identity is a series". It is:

* a weight identity is either a stored series or a documented weight-only code;
* every weight-only code is described in `original_weights_catalog`, with the
  Table 38 series it maps to or an explicit NULL when the source indexes no
  such level;
* no two workbook codes claim the same index series.

These tests hold that contract from both directions, so an audit that counts
W1 identities against `metadata` and calls the difference an orphan can be
answered with a query instead of an argument.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from scripts.original_weights import (
    assert_weight_identity_contract,
    upsert_original_weight_catalog,
    upsert_original_weights,
)

COLLECTED = datetime(2026, 8, 19)  # noqa: DTZ001
MONTH = date(2026, 6, 1)
DATASET = "ONS consumer price inflation updating weights, Annex A table W1-CPI"
SOURCE = "https://www.ons.gov.uk/economy/inflationandpriceindices"

# 01.1.1.1 "Rice": published as a weight, never indexed in Table 38.
WEIGHT_ONLY = "CPI_W1_01P1P1P1"
# 10 "Education": published as a weight and indexed, so it maps.
MAPPED = "CPI_W1_10"
EDUCATION = "CPI_INDEX_10_D7G8"


def _catalog(mapped_series_id: str = EDUCATION) -> dict[str, dict[str, str]]:
    return {
        WEIGHT_ONLY: {
            "code": "01.1.1.1",
            "name": "Rice",
            "native_id": "",
            "mapped_series_id": "",
            "dataset": DATASET,
            "source_url": SOURCE,
        },
        MAPPED: {
            "code": "10",
            "name": "Education",
            "native_id": "D7G8",
            "mapped_series_id": mapped_series_id,
            "dataset": DATASET,
            "source_url": SOURCE,
        },
    }


def _weights(*series_ids: str) -> list[dict[str, object]]:
    return [
        {
            "series_id": series_id,
            "reference_date": MONTH,
            "weight": 2.0,
            "weight_base_year": 2026,
        }
        for series_id in series_ids
    ]


def _add_series(engine: Engine, series_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO collector_ons_cpi.metadata (series_id, name, country, "
                "observation_count, source_url, collected_at) "
                "VALUES (:s, :s, 'GBP', 1, :u, :c)"
            ),
            {"s": series_id, "u": SOURCE, "c": COLLECTED},
        )


# -- the contract holds on the real shape ----------------------------------


def test_a_weight_only_identity_is_accepted_when_it_is_documented(engine: Engine) -> None:
    """The 01.1.1.1 case: a published weight with no published index."""
    _add_series(engine, EDUCATION)
    with engine.begin() as conn:
        upsert_original_weights(conn, _weights(WEIGHT_ONLY, MAPPED), COLLECTED)
        upsert_original_weight_catalog(conn, _catalog(), COLLECTED)
        assert_weight_identity_contract(conn)

    with engine.connect() as conn:
        mapped: object = conn.execute(
            text(
                "SELECT mapped_series_id FROM collector_ons_cpi.original_weights_catalog "
                "WHERE series_id = :s"
            ),
            {"s": WEIGHT_ONLY},
        ).scalar_one()
    assert mapped is None, "a weight with no published index must map to NULL, not to a guess"


def test_every_stored_weight_identity_can_be_accounted_for(engine: Engine) -> None:
    """The query an auditor runs: no W1 row is left without an explanation."""
    _add_series(engine, EDUCATION)
    with engine.begin() as conn:
        upsert_original_weights(conn, _weights(WEIGHT_ONLY, MAPPED, EDUCATION), COLLECTED)
        upsert_original_weight_catalog(conn, _catalog(), COLLECTED)

    with engine.connect() as conn:
        unaccounted: int = conn.execute(
            text(
                "SELECT COUNT(DISTINCT w.series_id) FROM collector_ons_cpi.original_weights w "
                "LEFT JOIN collector_ons_cpi.original_weights_catalog c "
                "  ON c.series_id = w.series_id "
                "LEFT JOIN collector_ons_cpi.metadata m ON m.series_id = w.series_id "
                "WHERE c.series_id IS NULL AND m.series_id IS NULL"
            )
        ).scalar_one()
    assert unaccounted == 0


# -- and refuses the three ways it can break -------------------------------


def test_an_undocumented_weight_identity_is_refused(engine: Engine) -> None:
    """A W1 code that is neither a series nor in the crosswalk is a real orphan."""
    with engine.begin() as conn:
        upsert_original_weights(conn, _weights("CPI_W1_99P9"), COLLECTED)
        with pytest.raises(ValueError, match="neither stored series nor documented"):
            assert_weight_identity_contract(conn)


def test_a_crosswalk_pointing_at_a_missing_series_is_refused(engine: Engine) -> None:
    """What a renamed or filtered-away Table 38 series looks like."""
    with engine.begin() as conn:
        upsert_original_weights(conn, _weights(WEIGHT_ONLY, MAPPED), COLLECTED)
        upsert_original_weight_catalog(conn, _catalog(), COLLECTED)
        with pytest.raises(ValueError, match="onto series that are not stored"):
            assert_weight_identity_contract(conn)


def test_two_codes_claiming_one_series_with_different_cdids_are_refused(
    engine: Engine,
) -> None:
    """Different CDIDs on one index means two real weights, so it must fail."""
    _add_series(engine, EDUCATION)
    catalog = _catalog()
    catalog[WEIGHT_ONLY]["mapped_series_id"] = EDUCATION
    with engine.begin() as conn:
        upsert_original_weights(conn, _weights(WEIGHT_ONLY, MAPPED), COLLECTED)
        upsert_original_weight_catalog(conn, catalog, COLLECTED)
        with pytest.raises(ValueError, match="disagree while claiming"):
            assert_weight_identity_contract(conn)


def test_two_codes_claiming_one_series_with_different_weights_are_refused(
    engine: Engine,
) -> None:
    """Same CDID but disagreeing weights is the double-count this guards."""
    _add_series(engine, EDUCATION)
    catalog = _catalog()
    catalog[WEIGHT_ONLY]["native_id"] = "D7G8"
    catalog[WEIGHT_ONLY]["mapped_series_id"] = EDUCATION
    rows = _weights(WEIGHT_ONLY, MAPPED)
    rows[0]["weight"] = 3.0
    with engine.begin() as conn:
        upsert_original_weights(conn, rows, COLLECTED)
        upsert_original_weight_catalog(conn, catalog, COLLECTED)
        with pytest.raises(ValueError, match="disagree while claiming"):
            assert_weight_identity_contract(conn)


def test_one_series_listed_at_two_classification_levels_is_accepted(
    engine: Engine,
) -> None:
    """The real W1 case: Education is published as both `10` and `10.0`.

    COICOP division 10 has a single group, so the workbook lists both levels
    under CDID CJUU with the same weight in all 228 published months. Refusing
    this would refuse the live source; accepting a collision blindly would hide
    a genuine double count, which the two tests above still catch.
    """
    _add_series(engine, EDUCATION)
    catalog = _catalog()
    catalog[WEIGHT_ONLY]["code"] = "10.0"
    catalog[WEIGHT_ONLY]["name"] = "Education"
    catalog[WEIGHT_ONLY]["native_id"] = "D7G8"
    catalog[WEIGHT_ONLY]["mapped_series_id"] = EDUCATION
    with engine.begin() as conn:
        upsert_original_weights(conn, _weights(WEIGHT_ONLY, MAPPED), COLLECTED)
        upsert_original_weight_catalog(conn, catalog, COLLECTED)
        assert_weight_identity_contract(conn)


# -- the crosswalk itself --------------------------------------------------


def test_the_crosswalk_is_idempotent(engine: Engine) -> None:
    """An unchanged rerun must not rewrite a single crosswalk row."""
    _add_series(engine, EDUCATION)
    with engine.begin() as conn:
        assert upsert_original_weight_catalog(conn, _catalog(), COLLECTED) == (2, 0)
    with engine.begin() as conn:
        assert upsert_original_weight_catalog(conn, _catalog(), COLLECTED) == (0, 0)


def test_a_relabelled_code_updates_in_place(engine: Engine) -> None:
    """The crosswalk describes what an identifier means; it carries no vintage."""
    _add_series(engine, EDUCATION)
    with engine.begin() as conn:
        upsert_original_weight_catalog(conn, _catalog(), COLLECTED)
    renamed = _catalog()
    renamed[WEIGHT_ONLY]["name"] = "Rice and rice products"
    with engine.begin() as conn:
        assert upsert_original_weight_catalog(conn, renamed, COLLECTED) == (0, 1)

    with engine.connect() as conn:
        rows: int = conn.execute(
            text("SELECT COUNT(*) FROM collector_ons_cpi.original_weights_catalog")
        ).scalar_one()
        name: str = conn.execute(
            text(
                "SELECT name FROM collector_ons_cpi.original_weights_catalog WHERE series_id = :s"
            ),
            {"s": WEIGHT_ONLY},
        ).scalar_one()
    assert rows == 2, "a relabelled code is corrected in place, not duplicated"
    assert name == "Rice and rice products"
