from datetime import date

from precon_lab.historical_codes import (
    build_production_code,
    build_test_code,
    derive_product_code,
    product_candidate,
)


def test_codes_requested_by_user():
    assert product_candidate("M12L-DIV-16042026") == "M12L-DIV"
    assert product_candidate("M12L-DIV-14D-30042026") == "M12L-DIV"
    assert product_candidate("M12L-DIV-20260416") == "M12L-DIV"

    assert build_production_code("M12L-DIV", date(2026, 4, 16)) == "M12L-DIV-16042026"
    assert build_test_code("M12L-DIV", 14, date(2026, 4, 30)) == "M12L-DIV-14D-30042026"


def test_legacy_mmdd_codes_are_normalized_with_real_dates():
    product = derive_product_code(
        [(1, "M12L-DIV-0105"), (2, "M12L-DIV-0105"), (3, "M12L-DIV-0105")],
        source_test_code="M12L-DIV-28D-0202",
        product_name="M12L DIV",
        source_file="M12L-DIV-28D-0202(0105).xlsx",
    )
    assert product == "M12L-DIV"
    assert build_production_code(product, date(2021, 1, 5)) == "M12L-DIV-05012021"
    assert build_test_code(product, 28, date(2021, 2, 2)) == "M12L-DIV-28D-02022021"


def test_trailing_specimen_number_is_removed_only_when_it_matches_ordinal():
    product = derive_product_code(
        [(1, "AR8-1"), (2, "AR8-2"), (3, "AR8-3")],
        source_test_code="AR8-1012",
    )
    assert product == "AR8"


def test_model_tokens_are_preserved():
    assert product_candidate("E14L-DIV-BL-M1-0916") == "E14L-DIV-BL-M1"
