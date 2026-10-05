from __future__ import annotations

from civillab_suite.app import SuiteController, bootstrap_shared_data
from civillab_suite.core.database import CoreDatabase
from civillab_suite.registry import create_default_registry
from civillab_suite.tools import TOOLS
from civillab_suite.ui.calendar_page import SharedCalendarPage
from civillab_suite.ui.catalog_page import AssayCatalogPage
from civillab_suite.ui.pie_page import SharedPiePage
from civillab_suite.ui.tools_page import SharedToolsPage


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
    assert isinstance(concrete.tools_page, SharedToolsPage)
    assert concrete.tools_page.tools is TOOLS
    labels = [concrete.tabs.tabText(i) for i in range(concrete.tabs.count())]
    assert labels.index("Herramientas") == labels.index("Normativas") + 1
    concrete.navigation_buttons[labels.index("Herramientas")].click()
    assert concrete.tabs.currentWidget() is concrete.tools_page

    controller.open_module("prefabricados")
    prefabricated = controller.module_windows["prefabricados"]
    pages = {name: page for name, page in prefabricated.pages}
    assert "Itinerario" not in pages
    assert isinstance(pages["Catálogo de Ensayos"], AssayCatalogPage)
    assert isinstance(pages["Plan de Inspección y Ensayo"], SharedPiePage)
    assert isinstance(pages["Calendario"], SharedCalendarPage)
    assert isinstance(pages["Herramientas"], SharedToolsPage)
    assert pages["Herramientas"].tools is TOOLS
    assert pages["Herramientas"] is not concrete.tools_page
    prefabricated.navigation_buttons[list(pages).index("Herramientas")].click()
    assert prefabricated.stack.currentWidget() is pages["Herramientas"]
    concrete.tools_page.open_tool(TOOLS[0].id)
    assert pages["Herramientas"].tabs.count() == 1
    assert any(item.requirements for item in controller.context.catalog.list_assays(
        "prefabricados"
    ))

    controller.return_home()
    assert controller.active_module_id is None
    for window in controller.module_windows.values():
        window.close()
    controller.shell.close()
    qapp.processEvents()
