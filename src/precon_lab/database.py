from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from typing import Iterator

from sqlalchemy import create_engine, event, or_, select, text
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session, joinedload, sessionmaker

from .config import database_url
from .historical_codes import build_production_code, build_test_code, derive_product_code
from .inspection_catalog import seed_inspection_catalog
from .models import Base, HistoricalTest, Product

_engine = None
_SessionFactory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = _make_engine(database_url())
    return _engine


def _make_engine(url):
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def configure(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA busy_timeout=10000")

    return engine


def use_database(path) -> None:
    global _engine
    if _engine is not None and _engine.url.database == str(path):
        return
    dispose_database_connections()
    _engine = _make_engine(f"sqlite:///{path.as_posix()}")


def initialize_at(path, *, seed_products=False) -> None:
    """Initialize a staging database without redirecting an active workspace."""
    global _engine, _SessionFactory
    previous_engine, previous_factory = _engine, _SessionFactory
    _engine, _SessionFactory = _make_engine(f"sqlite:///{path.as_posix()}"), None
    try:
        initialize_database(seed_products=seed_products)
    finally:
        dispose_database_connections()
        _engine, _SessionFactory = previous_engine, previous_factory


def get_session_factory():
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            future=True,
        )
    return _SessionFactory


def dispose_database_connections() -> None:
    """Release pooled SQLite handles before a full-suite data replacement."""

    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_historical_browser_columns() -> None:
    """
    Temporary SQLite migration for prototype 0.1.

    It preserves an existing database while adding the three columns used by
    the historical browser. Replace this with Alembic when formal migrations
    are introduced.
    """
    engine = get_engine()
    inspector = sqlalchemy_inspect(engine)
    if "prefabricados_historical_tests" not in inspector.get_table_names():
        return

    columns = {item["name"] for item in inspector.get_columns("prefabricados_historical_tests")}
    statements: list[str] = []

    if "product_code" not in columns:
        statements.append(
            "ALTER TABLE prefabricados_historical_tests "
            "ADD COLUMN product_code VARCHAR(160) NOT NULL DEFAULT ''"
        )
    if "production_code" not in columns:
        statements.append(
            "ALTER TABLE prefabricados_historical_tests "
            "ADD COLUMN production_code VARCHAR(220) NOT NULL DEFAULT ''"
        )
    if "test_code" not in columns:
        statements.append(
            "ALTER TABLE prefabricados_historical_tests "
            "ADD COLUMN test_code VARCHAR(220) NOT NULL DEFAULT ''"
        )

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_historical_tests_product_code "
                "ON prefabricados_historical_tests (product_code)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_historical_tests_production_code "
                "ON prefabricados_historical_tests (production_code)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_historical_tests_test_code "
                "ON prefabricados_historical_tests (test_code)"
            )
        )


def _ensure_inspection_catalog_columns() -> None:
    """Migración SQLite ligera para detalles por material y ensayo."""
    engine = get_engine()
    inspector = sqlalchemy_inspect(engine)
    if "prefabricados_test_applicabilities" not in inspector.get_table_names():
        return

    columns = {item["name"] for item in inspector.get_columns("prefabricados_test_applicabilities")}
    if "procedure_detail" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE prefabricados_test_applicabilities "
                    "ADD COLUMN procedure_detail TEXT NOT NULL DEFAULT ''"
                )
            )


def _backfill_historical_codes() -> None:
    with session_scope() as session:
        statement = (
            select(HistoricalTest)
            .options(joinedload(HistoricalTest.specimens))
            .where(
                or_(
                    HistoricalTest.product_code == "",
                    HistoricalTest.production_code == "",
                    HistoricalTest.test_code == "",
                )
            )
        )

        for item in session.scalars(statement).unique():
            if item.production_date is None and item.test_date is not None and item.target_age_days is not None:
                item.production_date = item.test_date - timedelta(days=item.target_age_days)

            product_code = item.product_code or derive_product_code(
                (
                    (specimen.ordinal, specimen.specimen_code)
                    for specimen in item.specimens
                ),
                product_name=item.product_name,
                source_file=item.source_file,
            )
            item.product_code = product_code
            item.production_code = item.production_code or build_production_code(
                product_code,
                item.production_date,
            )
            item.test_code = item.test_code or build_test_code(
                product_code,
                item.target_age_days,
                item.test_date,
            )


def initialize_database(*, seed_products=True) -> None:
    Base.metadata.create_all(get_engine())
    _ensure_historical_browser_columns()
    _ensure_inspection_catalog_columns()
    _backfill_historical_codes()
    if seed_products:
        seed_default_products()
    with session_scope() as session:
        seed_inspection_catalog(session)


def seed_default_products() -> None:
    defaults = [
        ("Bloque de concreto", "BLOQUE", "BLOCK"),
        ("Adoquín / elemento para flexotracción", "FLEX", "FLEXURE"),
    ]
    with session_scope() as session:
        existing = set(session.scalars(select(Product.code)).all())
        for name, code, category in defaults:
            if code not in existing:
                session.add(Product(name=name, code=code, category=category))
