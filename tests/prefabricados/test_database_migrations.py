from sqlalchemy import create_engine, inspect, text

from precon_lab import database


def test_legacy_applicabilities_gain_procedure_detail_column(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE test_applicabilities (id INTEGER PRIMARY KEY)"))

    monkeypatch.setattr(database, "get_engine", lambda: engine)
    database._ensure_inspection_catalog_columns()

    columns = {item["name"] for item in inspect(engine).get_columns("test_applicabilities")}
    assert "procedure_detail" in columns
