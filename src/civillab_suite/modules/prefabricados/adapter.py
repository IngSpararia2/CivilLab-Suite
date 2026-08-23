from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QApplication, QMainWindow

from civillab_suite.data_paths import prepare_prefabricados_data


def create_window(
    on_return_to_suite: Callable[[], None] | None = None,
    suite_context=None,
) -> QMainWindow:
    if QApplication.instance() is None:
        raise RuntimeError("CivilLab Suite debe crear QApplication antes de abrir Prefabricados.")

    prepare_prefabricados_data()
    from precon_lab.database import initialize_database
    from precon_lab.ui.main_window import MainWindow
    from precon_lab.ui.styles import APP_STYLESHEET
    from civillab_suite.ui.shared_controls import install_shared_control_tuning

    initialize_database()
    install_shared_control_tuning()
    catalog_page = pie_page = calendar_page = None
    if suite_context is not None:
        from precon_lab.config import database_path
        from civillab_suite.ui.calendar_page import SharedCalendarPage
        from civillab_suite.ui.catalog_page import AssayCatalogPage
        from civillab_suite.ui.pie_page import SharedPiePage

        suite_context.pie.import_prefabricados_legacy(database_path())
        catalog_page = AssayCatalogPage(suite_context.catalog, "prefabricados")
        pie_page = SharedPiePage(
            suite_context.pie,
            suite_context.catalog,
            suite_context.available_modules,
            "prefabricados",
        )
        calendar_page = SharedCalendarPage(
            suite_context.scheduling,
            suite_context.available_modules,
            "prefabricados",
            suite_context.navigate,
        )
    window = MainWindow(
        on_return_to_suite=on_return_to_suite,
        shared_catalog_page=catalog_page,
        shared_pie_page=pie_page,
        shared_calendar_page=calendar_page,
    )
    window.setStyleSheet(APP_STYLESHEET)
    return window
