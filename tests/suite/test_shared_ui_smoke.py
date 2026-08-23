from __future__ import annotations

from civillab_suite.app import SuiteController, bootstrap_shared_data
from civillab_suite.core.database import CoreDatabase
from civillab_suite.registry import create_default_registry
from civillab_suite.ui.calendar_page import SharedCalendarPage
from civillab_suite.ui.catalog_page import AssayCatalogPage
from civillab_suite.ui.pie_page import SharedPiePage


def test_suite_opens_shared_catalog_pie_and_calendar_in_both_areas(
    qapp, monkeypatch, tmp_path
):
    from concrete_mix_designer import config as concrete_config
    from precon_lab import database as prefabricados_database

    concrete_path = tmp_path / "concretos.sqlite3"
    monkeypatch.setattr(concrete_config, "DATABASE_PATH", concrete_path)
    monkeypatch.setenv("PRECON_LAB_DATA_DIR", str(tmp_path / "prefabricados"))
    monkeypatch.setattr(prefabricados_database, "_engine", None)
    monkeypatch.setattr(prefabricados_database, "_SessionFactory", None)

    registry = create_default_registry()
    database = CoreDatabase(tmp_path / "core.sqlite3")
    bootstrap_shared_data(registry, database)
    controller = SuiteController(registry, database)

    controller.open_module("concretos")
    concrete = controller.module_windows["concretos"]
    assert isinstance(concrete.catalog_page, AssayCatalogPage)
    assert isinstance(concrete.pie_page, SharedPiePage)
    assert isinstance(concrete.calendar_page, SharedCalendarPage)

    controller.open_module("prefabricados")
    prefabricated = controller.module_windows["prefabricados"]
    pages = {name: page for name, page in prefabricated.pages}
    assert "Itinerario" not in pages
    assert isinstance(pages["Catálogo de Ensayos"], AssayCatalogPage)
    assert isinstance(pages["Plan de Inspección y Ensayo"], SharedPiePage)
    assert isinstance(pages["Calendario"], SharedCalendarPage)
    assert any(item.requirements for item in controller.context.catalog.list_assays(
        "prefabricados"
    ))

    controller.return_home()
    assert controller.active_module_id is None
    for window in controller.module_windows.values():
        window.close()
    controller.shell.close()
    qapp.processEvents()
