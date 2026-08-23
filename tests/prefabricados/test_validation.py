import pytest

from precon_lab.services import ValidationError, parse_ages


def test_parse_ages_removes_duplicates_and_orders():
    assert parse_ages("28, 7,3,7,14") == [3, 7, 14, 28]


def test_parse_ages_rejects_empty():
    with pytest.raises(ValidationError):
        parse_ages("")
