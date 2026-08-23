from datetime import date

from precon_lab.historical_queries import (
    HistoricalFilters,
    count_historical_productions,
    query_historical_production_page,
)
from precon_lab.models import HistoricalTest, ImportBatch


def _add_test(session, *, suffix: str, product: str, production_date: date, age: int) -> None:
    imported = ImportBatch(
        file_hash=(suffix * 64)[:64],
        file_name=f"{product}-{age}D.xlsx",
        file_path=f"C:/demo/{product}-{age}D.xlsx",
        test_type="COMPRESSION",
        row_count=1,
        imported_count=1,
        status="COMPLETED",
    )
    imported.historical_tests.append(
        HistoricalTest(
            row_hash=((suffix.upper() or "X") * 64)[:64],
            test_type="COMPRESSION",
            product_code=product,
            production_code=f"{product}-{production_date:%d%m%Y}",
            test_code=f"{product}-{age}D",
            product_name=product,
            production_date=production_date,
            test_date=production_date,
            target_age_days=age,
            source_file=f"{product}-{age}D.xlsx",
            reading_status="OK",
        )
    )
    session.add(imported)


def test_production_pagination_and_sorting(session):
    _add_test(session, suffix="a", product="ZZZ", production_date=date(2026, 1, 1), age=7)
    _add_test(session, suffix="b", product="AAA", production_date=date(2026, 2, 1), age=7)
    _add_test(session, suffix="c", product="MMM", production_date=date(2026, 3, 1), age=7)
    _add_test(session, suffix="d", product="MMM", production_date=date(2026, 3, 1), age=28)
    session.commit()

    filters = HistoricalFilters()
    assert count_historical_productions(
        session,
        test_type="COMPRESSION",
        filters=filters,
    ) == 3

    first_page = query_historical_production_page(
        session,
        test_type="COMPRESSION",
        filters=filters,
        limit=2,
        offset=0,
        sort_field="date",
        descending=True,
    )
    assert [item.product_code for item in first_page] == ["MMM", "AAA"]
    assert first_page[0].test_count == 2

    second_page = query_historical_production_page(
        session,
        test_type="COMPRESSION",
        filters=filters,
        limit=2,
        offset=2,
        sort_field="date",
        descending=True,
    )
    assert [item.product_code for item in second_page] == ["ZZZ"]

    alphabetical = query_historical_production_page(
        session,
        test_type="COMPRESSION",
        filters=filters,
        limit=10,
        offset=0,
        sort_field="product",
        descending=False,
    )
    assert [item.product_code for item in alphabetical] == ["AAA", "MMM", "ZZZ"]
