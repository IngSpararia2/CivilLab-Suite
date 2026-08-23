from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from precon_lab.models import Base, Product


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Product(name="Bloque de concreto", code="BLOQUE", category="BLOCK"),
                Product(name="Adoquín 10x20x6", code="AR6", category="FLEXURE"),
            ]
        )
        session.commit()
        yield session
