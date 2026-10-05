from datetime import date

from precon_lab.historical_queries import HistoricalFilters, query_historical_groups
from precon_lab.models import HistoricalSpecimen, HistoricalTest, ImportBatch


def test_query_builds_three_level_compression_hierarchy(session):
    imported = ImportBatch(
        file_hash="a" * 64,
        file_name="M12L-DIV-3D-19042026.xlsx",
        file_path="C:/demo/M12L-DIV-3D-19042026.xlsx",
        test_type="COMPRESSION",
        row_count=1,
        imported_count=1,
        status="COMPLETED",
    )
    test = HistoricalTest(
        import_batch=imported,
        row_hash="b" * 64,
        test_type="COMPRESSION",
        product_code="M12L-DIV",
        production_code="M12L-DIV-16042026",
        test_code="M12L-DIV-3D-19042026",
        product_name="Muro Cell liso 12 cm divisorio",
        production_date=date(2026, 4, 16),
        test_date=date(2026, 4, 19),
        target_age_days=3,
        source_file="M12L-DIV-3D-19042026.xlsx",
        reading_status="OK",
        absorption_avg=5.0,
        strength_avg=12.0,
    )
    test.specimens.extend(
        [
            HistoricalSpecimen(
                ordinal=1,
                specimen_code="M12L-DIV-16042026",
                natural_mass=10,
                dry_mass=9,
                immersed_mass=5,
                saturated_mass=10,
                density=2000,
                absorption=4,
                maximum_load=100,
                strength=11,
            ),
            HistoricalSpecimen(
                ordinal=2,
                specimen_code="M12L-DIV-16042026",
                natural_mass=11,
                dry_mass=10,
                immersed_mass=6,
                saturated_mass=11,
                density=2100,
                absorption=5,
                maximum_load=110,
                strength=12,
            ),
            HistoricalSpecimen(
                ordinal=3,
                specimen_code="M12L-DIV-16042026",
                natural_mass=12,
                dry_mass=11,
                immersed_mass=7,
                saturated_mass=12,
                density=2200,
                absorption=6,
                maximum_load=120,
                strength=13,
            ),
        ]
    )
    session.add(imported)
    session.commit()

    groups = query_historical_groups(
        session,
        test_type="COMPRESSION",
        filters=HistoricalFilters(product_text="M12L", date_from=date(2026, 4, 1)),
    )

    assert len(groups) == 1
    assert groups[0].production_code == "M12L-DIV-16042026"
    assert len(groups[0].tests) == 1
    result = groups[0].tests[0]
    assert result.test_code == "M12L-DIV-3D-19042026"
    assert result.natural_mass_avg == 11
    assert result.maximum_load_avg == 110
    assert result.absorption_avg == 5.0
    assert len(result.specimens) == 3


def test_filters_by_reading_status(session):
    imported = ImportBatch(
        file_hash="c" * 64,
        file_name="demo.xlsx",
        file_path="demo.xlsx",
        test_type="FLEXURE",
        row_count=1,
        imported_count=1,
        status="COMPLETED",
    )
    imported.historical_tests.append(
        HistoricalTest(
            row_hash="d" * 64,
            test_type="FLEXURE",
            product_code="AR6",
            production_code="AR6-01012026",
            test_code="AR6-7D-08012026",
            product_name="Adoquín 10x20x6",
            production_date=date(2026, 1, 1),
            test_date=date(2026, 1, 8),
            target_age_days=7,
            reading_status="Revisión parcial",
        )
    )
    session.add(imported)
    session.commit()

    groups = query_historical_groups(
        session,
        test_type="FLEXURE",
        filters=HistoricalFilters(reading_status="OK"),
    )
    assert groups == []
