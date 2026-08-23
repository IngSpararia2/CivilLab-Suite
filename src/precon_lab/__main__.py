from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .config import APP_ICON_PATH, APP_NAME, APP_VERSION
from .database import initialize_database
from .ui.main_window import MainWindow
from .ui.splash_screen import AppSplashScreen
from .ui.styles import APP_STYLESHEET
from civillab_suite.ui.shared_controls import install_shared_control_tuning


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("PRECONCRETOS")
    app.setOrganizationDomain("prefabricadoslab.local")
    app.setStyle("Fusion")
    install_shared_control_tuning()
    app.setStyleSheet(APP_STYLESHEET)
    if APP_ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))

    splash = AppSplashScreen()
    splash.show()
    splash.schedule_credit_animation()
    app.processEvents()

    initialize_database()
    window = MainWindow()

    def show_main_window() -> None:
        window.showMaximized()
        splash.finish(window)

    QTimer.singleShot(AppSplashScreen.DISPLAY_DURATION_MS, show_main_window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
