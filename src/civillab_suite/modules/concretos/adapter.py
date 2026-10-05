from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QApplication, QMainWindow


def create_window(
    on_return_to_suite: Callable[[], None] | None = None,
    suite_context=None,
) -> QMainWindow:
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("CivilLab Suite debe crear QApplication antes de abrir Concretos.")

    from civillab_suite.ui.shared_controls import (
        install_shared_control_tuning,
        tune_shared_controls,
    )
    from civillab_suite.ui.tools_page import SharedToolsPage
    from concrete_mix_designer.config import DATABASE_PATH
    from concrete_mix_designer.data.database import MaterialRepository
    from concrete_mix_designer.data.laboratory_repository import LaboratoryRepository
    from concrete_mix_designer.services.app_state import AppState
    from concrete_mix_designer.ui.main_window import MainWindow
    from concrete_mix_designer.ui.styles import APP_STYLESHEET

    install_shared_control_tuning()

    material_repository = MaterialRepository(DATABASE_PATH)
    laboratory_repository = LaboratoryRepository(DATABASE_PATH)
    state = AppState(material_repository, laboratory_repository)
    catalog_page = pie_page = calendar_page = None
    if suite_context is not None:
        from civillab_suite.ui.calendar_page import SharedCalendarPage
        from civillab_suite.ui.catalog_page import AssayCatalogPage
        from civillab_suite.ui.pie_page import SharedPiePage

        suite_context.pie.import_concretos_legacy(DATABASE_PATH)
        catalog_page = AssayCatalogPage(suite_context.catalog, "concretos")
        pie_page = SharedPiePage(
            suite_context.pie,
            suite_context.catalog,
            suite_context.available_modules,
            "concretos",
        )
        calendar_page = SharedCalendarPage(
            suite_context.scheduling,
            suite_context.available_modules,
            "concretos",
            suite_context.navigate,
        )
    window = MainWindow(
        state,
        on_return_to_suite=on_return_to_suite,
        shared_catalog_page=catalog_page,
        shared_pie_page=pie_page,
        shared_calendar_page=calendar_page,
        shared_tools_page=SharedToolsPage(),
    )
    window.setStyleSheet(APP_STYLESHEET)
    tune_shared_controls(window, light_surfaces=True)
    return window
