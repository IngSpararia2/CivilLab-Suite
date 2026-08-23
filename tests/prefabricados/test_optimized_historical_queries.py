from datetime import date

from precon_lab.historical_queries import (
    HistoricalFilters,
    query_historical_productions,
    query_historical_specimens,
    query_historical_tests_for_production,
)
from precon_lab.models import HistoricalSpecimen, HistoricalTest, ImportBatch


def test_master_detail_queries_load_each_level_separately(session):
    imported = ImportBatch(
        file_hash="e" * 64,
        file_name="M12L-DIV-7D-23042026.xlsx",
        file_path="C:/demo/M12L-DIV-7D-23042026.xlsx",
        test_type="COMPRESSION",
        row_count=1,
        imported_count=1,
        status="COMPLETED",
    )
    test = HistoricalTest(
        import_batch=imported,
        row_hash="f" * 64,
        test_type="COMPRESSION",
        product_code="M12L-DIV",
        production_code="M12L-DIV-16042026",
        test_code="M12L-DIV-7D-23042026",
        product_name="Muro Cell liso 12 cm divisorio",
        production_date=date(2026, 4, 16),
        test_date=date(2026, 4, 23),
        target_age_days=7,
        source_file="M12L-DIV-7D-23042026.xlsx",
        reading_status="OK",
        absorption_avg=5.5,
        strength_avg=14.0,
    )
    test.specimens.extend(
        [
            HistoricalSpecimen(
                ordinal=1,
                specimen_code="M12L-DIV-16042026-1",
                natural_mass=10,
                dry_mass=9,
                maximum_load=100,
                strength=13,
            ),
            HistoricalSpecimen(
                ordinal=2,
                specimen_code="M12L-DIV-16042026-2",
                natural_mass=12,
                dry_mass=11,
                maximum_load=120,
                strength=15,
            ),
        ]
    )
    session.add(imported)
    session.commit()

    filters = HistoricalFilters(product_text="M12L")
    productions = query_historical_productions(
        session,
        test_type="COMPRESSION",
        filters=filters,
    )
    assert len(productions) == 1
    assert productions[0].production_code == "M12L-DIV-16042026"
    assert productions[0].test_count == 1

    tests = query_historical_tests_for_production(
        session,
        test_type="COMPRESSION",
        product_code=productions[0].product_code,
        production_date=productions[0].production_date,
        filters=filters,
    )
    assert len(tests) == 1
    assert tests[0].natural_mass_avg == 11
    assert tests[0].maximum_load_avg == 110
    assert tests[0].strength_avg == 14.0

    specimens = query_historical_specimens(
        session,
        historical_test_id=tests[0].id,
    )
    assert [item.ordinal for item in specimens] == [1, 2]
