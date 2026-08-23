from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QApplication, QMainWindow

from civillab_suite.data_paths import prepare_prefabricados_data


def create_window(on_return_to_suite: Callable[[], None] | None = None) -> QMainWindow:
    if QApplication.instance() is None:
        raise RuntimeError("CivilLab Suite debe crear QApplication antes de abrir Prefabricados.")

    prepare_prefabricados_data()
    from precon_lab.database import initialize_database
    from precon_lab.ui.main_window import MainWindow
    from precon_lab.ui.styles import APP_STYLESHEET

    initialize_database()
    window = MainWindow(on_return_to_suite=on_return_to_suite)
    window.setStyleSheet(APP_STYLESHEET)
    return window
