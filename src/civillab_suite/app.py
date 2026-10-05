from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from .config import APP_NAME, APP_VERSION, core_database_path
from .context import SuiteContext, build_suite_context
from .core.database import CoreDatabase
from .core.scheduling import NavigationTarget
from .registry import ModuleRegistry, create_default_registry
from .ui.shell import SuiteWindow


def bootstrap_shared_data(registry: ModuleRegistry, database: CoreDatabase) -> Path:
    from civillab_suite.storage import migrate_workspace
    from precon_lab.database import use_database

    migrate_workspace(database.path)
    use_database(database.path)
    return database.path


class SuiteController(QObject):
    def __init__(self, registry: ModuleRegistry, database: CoreDatabase):
        super().__init__()
        self.registry = registry
        self.database = database
        self.shell = SuiteWindow(registry)
        self.shell.module_requested.connect(self.open_module)
        self.shell.prepare_for_data_import.connect(self.prepare_for_data_import)
        self.shell.restart_required.connect(QApplication.instance().quit)
        self.module_windows: dict[str, QMainWindow] = {}
        self.active_module_id: str | None = None
        self.context: SuiteContext = build_suite_context(
            database, registry, self.navigate_to_activity
        )

    def open_module(self, module_id: str) -> None:
        if not self.registry.is_enabled(module_id):
            return
        descriptor = self.registry.get(module_id)
        try:
            window = self.module_windows.get(module_id)
            if window is None:
                factory = descriptor.load_entrypoint()
                window = factory(
                    on_return_to_suite=self.return_home,
                    suite_context=self.context,
                )
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

    def navigate_to_activity(self, target: NavigationTarget) -> None:
        """Open an area and delegate record-level navigation to its adapter window."""

        if target.module_id is None:
            window = self.module_windows.get(self.active_module_id or "")
            if window is not None and hasattr(window, "navigate_to_activity"):
                window.navigate_to_activity(target)
            return
        self.open_module(target.module_id)
        window = self.module_windows.get(target.module_id)
        if window is not None and hasattr(window, "navigate_to_activity"):
            window.navigate_to_activity(target)

    def return_home(self) -> None:
        if self.active_module_id is not None:
            self.module_windows[self.active_module_id].hide()
        self.active_module_id = None
        self.shell.showMaximized()
        self.shell.raise_()
        self.shell.activateWindow()

    def prepare_for_data_import(self) -> None:
        """Drop module windows and pooled handles before replacing data files."""

        for window in self.module_windows.values():
            window.close()
            window.deleteLater()
        self.module_windows.clear()
        self.active_module_id = None
        from precon_lab.database import dispose_database_connections

        dispose_database_connections()


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


def main(initial_module_id: str | None = None) -> int:
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
    from civillab_suite.config import suite_data_dir
    from civillab_suite.storage import migrate_workspace
    from concrete_mix_designer.config import LEGACY_DATABASE_PATH
    from precon_lab.config import legacy_database_path

    legacy_prefab = suite_data_dir() / "prefabricados" / "precon_lab.db"
    if not legacy_prefab.exists():
        legacy_prefab = legacy_database_path()
    try:
        migrate_workspace(database.path, LEGACY_DATABASE_PATH, legacy_prefab)
        bootstrap_shared_data(registry, database)
    except Exception as error:
        QMessageBox.critical(None, "No se pudo preparar el entorno", str(error))
        return 1
    controller = SuiteController(registry, database)
    app.suite_controller = controller
    if initial_module_id:
        controller.open_module(initial_module_id)
    else:
        controller.shell.showMaximized()
    return app.exec()
