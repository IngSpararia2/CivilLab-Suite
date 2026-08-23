from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from .config import APP_NAME, APP_VERSION, core_database_path
from .core.database import CoreDatabase
from .data_paths import prepare_prefabricados_data
from .registry import ModuleRegistry, create_default_registry
from .ui.shell import SuiteWindow


def bootstrap_shared_data(registry: ModuleRegistry, database: CoreDatabase) -> Path:
    database.initialize()
    database.sync_modules(registry.all())

    prefabricados_database = prepare_prefabricados_data()
    from precon_lab.database import initialize_database

    initialize_database()
    database.sync_prefabricados_catalog(prefabricados_database)
    return prefabricados_database


class SuiteController(QObject):
    def __init__(self, registry: ModuleRegistry, database: CoreDatabase):
        super().__init__()
        self.registry = registry
        self.database = database
        self.shell = SuiteWindow(registry)
        self.shell.module_requested.connect(self.open_module)
        self.module_windows: dict[str, QMainWindow] = {}
        self.active_module_id: str | None = None

    def open_module(self, module_id: str) -> None:
        if not self.registry.is_enabled(module_id):
            return
        descriptor = self.registry.get(module_id)
        try:
            window = self.module_windows.get(module_id)
            if window is None:
                factory = descriptor.load_entrypoint()
                window = factory(on_return_to_suite=self.return_home)
                self.module_windows[module_id] = window
        except Exception as error:
            QMessageBox.critical(
                self.shell,
                f"No se pudo abrir {descriptor.name}",
                str(error),
            )
            return

        if self.active_module_id and self.active_module_id != module_id:
            self.module_windows[self.active_module_id].hide()
        self.active_module_id = module_id
        self.shell.hide()
        window.showMaximized()
        window.raise_()
        window.activateWindow()

    def return_home(self) -> None:
        if self.active_module_id is not None:
            self.module_windows[self.active_module_id].hide()
        self.active_module_id = None
        self.shell.showMaximized()
        self.shell.raise_()
        self.shell.activateWindow()


def create_application(argv: list[str] | None = None) -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("Ing. Samuel Parariá")
    app.setOrganizationDomain("civillab.local")
    app.setStyle("Fusion")
    return app


def main() -> int:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "IngSpararia2.CivilLabSuite"
            )
        except (AttributeError, OSError):
            pass

    app = create_application()
    registry = create_default_registry()
    database = CoreDatabase(core_database_path())
    bootstrap_shared_data(registry, database)
    controller = SuiteController(registry, database)
    app.suite_controller = controller
    controller.shell.showMaximized()
    return app.exec()
