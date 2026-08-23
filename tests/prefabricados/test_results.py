from datetime import date

from sqlalchemy import select

from precon_lab.models import Product, SampleSet
from precon_lab.services import create_production, save_provisional_result


def test_save_provisional_result(session):
    product = session.scalar(select(Product).where(Product.category == "BLOCK"))
    create_production(
        session,
        product_id=product.id,
        production_date=date(2026, 7, 1),
        lot_code="L-RESULT",
        ages=[7],
    )
    session.commit()
    sample_set = session.scalar(select(SampleSet).where(SampleSet.purpose == "COMPRESSION"))

    result = save_provisional_result(
        session,
        sample_set_id=sample_set.id,
        test_date=date(2026, 7, 8),
        strength_avg=12.8,
        notes="Registro rápido",
    )
    session.commit()

    assert result.status == "PROVISIONAL"
    assert result.strength_avg == 12.8
    assert sample_set.status == "TESTED"
