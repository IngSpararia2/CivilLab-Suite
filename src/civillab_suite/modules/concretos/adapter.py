from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QApplication, QMainWindow


def create_window(on_return_to_suite: Callable[[], None] | None = None) -> QMainWindow:
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("CivilLab Suite debe crear QApplication antes de abrir Concretos.")

    from concrete_mix_designer.config import DATABASE_PATH
    from concrete_mix_designer.data.database import MaterialRepository
    from concrete_mix_designer.data.laboratory_repository import LaboratoryRepository
    from concrete_mix_designer.services.app_state import AppState
    from concrete_mix_designer.ui.main_window import MainWindow
    from concrete_mix_designer.ui.styles import APP_STYLESHEET
    from concrete_mix_designer.ui.widgets.combo_popup import ComboPopupSizer

    if not hasattr(app, "combo_popup_sizer"):
        app.combo_popup_sizer = ComboPopupSizer(app)
        app.installEventFilter(app.combo_popup_sizer)

    material_repository = MaterialRepository(DATABASE_PATH)
    laboratory_repository = LaboratoryRepository(DATABASE_PATH)
    state = AppState(material_repository, laboratory_repository)
    window = MainWindow(state, on_return_to_suite=on_return_to_suite)
    window.setStyleSheet(APP_STYLESHEET)
    return window
