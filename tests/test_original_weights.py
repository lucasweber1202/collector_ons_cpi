"""Protect official weights that have no published Table 38 index."""

from datetime import date

from scripts import extract
from tests.test_weight_matching import CATALOG, _workbook


def test_subclass_weights_are_preserved_without_fake_index_metadata() -> None:
    blob = _workbook([("10 Education", 34.0), ("01.1.1.1 Rice", 2.0)])
    extract.parse_weights_workbook(blob, CATALOG)
    original = extract.get_original_weights()
    assert sorted(original[date(2026, 2, 1)].values()) == [2.0, 34.0]
    assert len(extract.get_original_weight_catalog()) == 2


def test_unknown_ambiguous_node_is_rejected() -> None:
    catalog = {
        key: {"family": "COICOP", "node": "D10", "native_id": key, "name": "Education"}
        for key in ("ONE", "TWO")
    }
    import pytest

    with pytest.raises(ValueError, match="Ambiguous"):
        extract.parse_weights_workbook(_workbook([("10 Education", 34.0)]), catalog)
