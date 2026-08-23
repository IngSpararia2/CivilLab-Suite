from datetime import date

import pandas as pd
from sqlalchemy import func, select

from precon_lab.importers import import_summary_file
from precon_lab.models import HistoricalSpecimen, HistoricalTest, Product
from precon_lab.services import create_production, save_provisional_result


def test_import_compression_and_prevent_duplicate_file(session, tmp_path):
    product = session.scalar(select(Product).where(Product.category == "BLOCK"))
    create_production(
        session,
        product_id=product.id,
        production_date=date(2026, 7, 1),
        lot_code="L-IMP",
        ages=[7],
    )
    session.commit()

    from precon_lab.models import SampleSet

    sample_set = session.scalar(select(SampleSet).where(SampleSet.purpose == "COMPRESSION"))
    save_provisional_result(
        session,
        sample_set_id=sample_set.id,
        test_date=date(2026, 7, 8),
        strength_avg=12.8,
    )
    session.commit()

    dataframe = pd.DataFrame(
        [
            {
                "Nombre del Archivo": "demo.xlsx",
                "fecha de ensayo": "2026-07-08",
                "material": "Bloque de concreto",
                "Numero de Informe": "100",
                "bloque 1 fecha de elaboracion": "2026-07-01",
                "bloque 1 edad": 7,
                "bloque 1 edad calculada": 7,
                "Bloque 1 Id. Muestra": "B1",
                "Bloque 1 Material": "Bloque de concreto",
                "Bloque 1 Carga Maxima": 100,
                "Bloque 1 f'c Neta": 12.7,
                "Bloque 2 Id. Muestra": "B2",
                "Bloque 2 Material": "Bloque de concreto",
                "Bloque 2 Carga Maxima": 110,
                "Bloque 2 f'c Neta": 12.8,
                "Bloque 3 Id. Muestra": "B3",
                "Bloque 3 Material": "Bloque de concreto",
                "Bloque 3 Carga Maxima": 120,
                "Bloque 3 f'c Neta": 12.9,
                "Absorcion Promedio": 6.1,
                "Densidad Promedio": 2100,
                "f'c Promedio": 12.8,
                "Ruta relativa": "2026/demo.xlsx",
                "Estado de lectura": "OK",
                "Incidencias": "",
            }
        ]
    )
    path = tmp_path / "Resumen_Compresion.xlsx"
    dataframe.to_excel(path, sheet_name="Resumen", index=False)

    report = import_summary_file(session, path)
    session.commit()
    assert report.imported_rows == 1
    assert report.reconciled_rows == 1
    assert session.scalar(select(func.count()).select_from(HistoricalTest)) == 1
    assert session.scalar(select(func.count()).select_from(HistoricalSpecimen)) == 3
    assert sample_set.result.status == "CONCILIATED"
    assert sample_set.result.absorption_avg == 6.1

    duplicate = import_summary_file(session, path)
    assert duplicate.duplicate_file is True
