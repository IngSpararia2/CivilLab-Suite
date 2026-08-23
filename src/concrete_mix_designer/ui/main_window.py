from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from concrete_mix_designer.config import (
    APP_ICON_PATH,
    APP_NAME,
    APP_VERSION,
    SIDEBAR_LOGO_PATH,
)
from concrete_mix_designer.domain.metadata_models import DesignSpecification
from concrete_mix_designer.services.app_state import AppState
from concrete_mix_designer.ui.dialogs.design_dialogs import SaveDesignDialog
from concrete_mix_designer.ui.pages.dashboard_page import DashboardPage
from concrete_mix_designer.ui.pages.calendar_page import LaboratoryCalendarPage
from concrete_mix_designer.ui.pages.design_library_page import DesignLibraryPage
from concrete_mix_designer.ui.pages.materials_page import MaterialsPage
from concrete_mix_designer.ui.pages.production_page import ProductionPage
from concrete_mix_designer.ui.pages.results_page import ResultsPage
from concrete_mix_designer.ui.pages.standards_page import StandardsPage
from concrete_mix_designer.ui.pages.workspace_page import WorkspacePage


class MainWindow(QMainWindow):
    SIDEBAR_COLLAPSED_WIDTH = 64
    SIDEBAR_EXPANDED_WIDTH = 252

    def __init__(
        self,
        state: AppState,
        *,
        on_return_to_suite: Callable[[], None] | None = None,
        shared_catalog_page: QWidget | None = None,
        shared_pie_page: QWidget | None = None,
        shared_calendar_page: QWidget | None = None,
    ):
        super().__init__()
        self.state = state
        self._on_return_to_suite = on_return_to_suite
        self.setWindowTitle(f"{APP_NAME} · v{APP_VERSION}")
        self.resize(1440, 900)
        self.setMinimumSize(1024, 700)
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))

        self.tabs = QTabWidget()
        self.tabs.setObjectName("MainNavigation")
        self.tabs.tabBar().setObjectName("MainTabBar")
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.tabs.tabBar().setElideMode(Qt.ElideRight)
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().hide()
        self.dashboard_page = DashboardPage(state)
        self.workspace_page = WorkspacePage(state)
        self.workspace_page.save_design_button.clicked.connect(
            self._save_design_to_library
        )
        self.laboratory_tab = self.workspace_page
        self.results_page = ResultsPage(state)
        self.design_library_page = DesignLibraryPage(state)
        self.production_page = ProductionPage(state)
        self.calendar_page = shared_calendar_page or LaboratoryCalendarPage(state)
        self.materials_page = MaterialsPage(state)
        self.standards_page = StandardsPage()
        self.catalog_page = shared_catalog_page
        self.pie_page = shared_pie_page

        tab_definitions = [
            (self.dashboard_page, "Configurar", "1 · Configuración inicial"),
            (self.laboratory_tab, "Laboratorio", "2 · Diseño de mezcla"),
            (self.results_page, "Dosificación", "3 · Dosificación y registro"),
            (self.design_library_page, "Diseños", "4 · Diseños guardados"),
            (self.production_page, "Producción", "5 · Producción y ensayos"),
            (self.calendar_page, "Calendario", "6 · Calendario de laboratorio"),
        ]
        if self.pie_page is not None:
            tab_definitions.append((self.pie_page, "PIE", "7 · Plan de Inspección y Ensayo"))
        tab_definitions.append((self.materials_page, "Materiales", "8 · Gestor de materiales"))
        if self.catalog_page is not None:
            tab_definitions.append(
                (self.catalog_page, "Catálogo", "9 · Catálogo canónico de ensayos")
            )
        # The technical library remains available because it contains design guidance
        # beyond the canonical assay catalog.
        tab_definitions.append(
            (self.standards_page, "Normativas", "10 · Biblioteca de normativas")
        )
        for page, label, tooltip in tab_definitions:
            index = self.tabs.addTab(page, label)
            self.tabs.setTabToolTip(index, tooltip)

        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self._build_sidebar(tab_definitions))
        central_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self.tabs.currentChanged.connect(self._sync_sidebar_selection)
        self._set_sidebar_expanded(False)
        self._sync_sidebar_selection(self.tabs.currentIndex())
        QApplication.instance().installEventFilter(self)

        self.design_library_page.open_laboratory_requested.connect(
            lambda: self.tabs.setCurrentWidget(self.laboratory_tab)
        )
        self.results_page.production_created.connect(self._open_production)
        if hasattr(self.calendar_page, "open_production_requested"):
            self.calendar_page.open_production_requested.connect(self._open_production)

        self._build_menu()
        self.statusBar().showMessage("Listo")
        self.credit_label = QLabel("Ing. Samuel Parariá · Derechos reservados")
        self.credit_label.setObjectName("CopyrightCredit")
        self.credit_label.setToolTip(
            "Aplicación desarrollada por Ing. Samuel Parariá — Derechos reservados."
        )
        self.statusBar().addPermanentWidget(self.credit_label)
        state.message.connect(self.statusBar().showMessage)

    def _build_sidebar(self, tab_definitions: tuple) -> QFrame:
        self.sidebar = QFrame()
        self.sidebar.setObjectName("AppSidebar")
        self.sidebar.setMinimumWidth(self.SIDEBAR_COLLAPSED_WIDTH)
        self.sidebar.setMaximumWidth(self.SIDEBAR_COLLAPSED_WIDTH)

        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignTop)

        logo = QLabel()
        logo.setObjectName("AppLogo")
        logo.setFixedSize(46, 46)
        logo.setAlignment(Qt.AlignCenter)
        logo.setAccessibleName("Icono de Concretos Lab")
        if SIDEBAR_LOGO_PATH.exists():
            pixmap = QPixmap(str(SIDEBAR_LOGO_PATH))
            logo.setPixmap(
                pixmap.scaled(
                    logo.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

        self.sidebar_title = QLabel(APP_NAME)
        self.sidebar_title.setObjectName("SidebarBrandTitle")
        self.sidebar_title.setAlignment(Qt.AlignCenter)

        self.sidebar_version = QLabel(f"v{APP_VERSION}")
        self.sidebar_version.setObjectName("SidebarVersion")
        self.sidebar_version.setAlignment(Qt.AlignCenter)

        self.sidebar_toggle = QToolButton()
        self.sidebar_toggle.setObjectName("SidebarToggle")
        self.sidebar_toggle.setText("☰")
        self.sidebar_toggle.setFixedHeight(42)
        self.sidebar_toggle.setToolTip("Mostrar navegación")
        self.sidebar_toggle.setAccessibleName("Mostrar u ocultar navegación")
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)

        self.navigation_container = QWidget()
        self.navigation_container.setObjectName("SidebarNavigation")
        navigation_layout = QVBoxLayout(self.navigation_container)
        navigation_layout.setContentsMargins(0, 8, 0, 0)
        navigation_layout.setSpacing(5)

        self.navigation_group = QButtonGroup(self)
        self.navigation_group.setExclusive(True)
        self.navigation_buttons: list[QPushButton] = []
        for index, (_page, label, tooltip) in enumerate(tab_definitions):
            button = QPushButton(label)
            button.setObjectName("SidebarNavButton")
            button.setCheckable(True)
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.clicked.connect(
                lambda checked=False, page_index=index: self.tabs.setCurrentIndex(
                    page_index
                )
            )
            self.navigation_group.addButton(button, index)
            self.navigation_buttons.append(button)
            navigation_layout.addWidget(button)
        navigation_layout.addStretch()

        layout.addWidget(logo, 0, Qt.AlignHCenter)
        layout.addWidget(self.sidebar_toggle)
        layout.addWidget(self.sidebar_title)
        layout.addWidget(self.sidebar_version)
        layout.addWidget(self.navigation_container, 1)
        return self.sidebar

    def _toggle_sidebar(self) -> None:
        self._set_sidebar_expanded(not self.sidebar_expanded)

    def _set_sidebar_expanded(self, expanded: bool) -> None:
        self.sidebar_expanded = expanded
        width = (
            self.SIDEBAR_EXPANDED_WIDTH
            if expanded
            else self.SIDEBAR_COLLAPSED_WIDTH
        )
        self.sidebar.setMinimumWidth(width)
        self.sidebar.setMaximumWidth(width)
        self.sidebar_title.setVisible(expanded)
        self.sidebar_version.setVisible(expanded)
        self.navigation_container.setVisible(expanded)
        self.sidebar_toggle.setText("☰")
        self.sidebar_toggle.setToolTip(
            "Ocultar navegación" if expanded else "Mostrar navegación"
        )

    def _sync_sidebar_selection(self, index: int) -> None:
        if 0 <= index < len(self.navigation_buttons):
            self.navigation_buttons[index].setChecked(True)

    def eventFilter(self, watched, event) -> bool:
        if (
            getattr(self, "sidebar_expanded", False)
            and event.type() == QEvent.MouseButtonPress
            and isinstance(watched, QWidget)
            and watched is not self.sidebar
            and not self.sidebar.isAncestorOf(watched)
        ):
            self._set_sidebar_expanded(False)
        return super().eventFilter(watched, event)

    def _existing_groups(self) -> list[str]:
        return self.state.design_groups

    def _save_design_to_library(self) -> None:
        suggested_name = ""
        suggested_group = ""
        suggested_specification = DesignSpecification.from_mix_design(self.state.design)
        current_id = self.state.current_saved_design_id
        if current_id is not None:
            record = self.state.laboratory_repository.get_design(current_id)
            if record is not None:
                suggested_name = record.name
                suggested_group = record.group_name
                suggested_specification = self.state.get_design_specification(record.id)

        dialog = SaveDesignDialog(
            suggested_name=suggested_name,
            suggested_group=suggested_group,
            existing_groups=self._existing_groups(),
            suggested_specification=suggested_specification,
            parent=self,
        )
        if not dialog.exec():
            return
        try:
            self.state.save_current_design_to_library(
                dialog.design_name,
                dialog.description,
                dialog.group_name,
                dialog.specification,
            )
        except Exception as error:
            QMessageBox.critical(self, "No se pudo guardar", str(error))

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Archivo")

        if self._on_return_to_suite is not None:
            suite_action = QAction("Volver a CivilLab Suite", self)
            suite_action.setShortcut("Ctrl+Shift+H")
            suite_action.triggered.connect(self._return_to_suite)
            file_menu.addAction(suite_action)
            file_menu.addSeparator()

        save_library_action = QAction("Guardar diseño calculado…", self)
        save_library_action.setShortcut("Ctrl+S")
        save_library_action.triggered.connect(self._save_design_to_library)
        file_menu.addAction(save_library_action)

        file_menu.addSeparator()
        export_action = QAction("Exportar diseño como JSON…", self)
        export_action.triggered.connect(self._save_design)
        file_menu.addAction(export_action)

        load_action = QAction("Importar diseño JSON…", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self._load_design)
        file_menu.addAction(load_action)

        file_menu.addSeparator()
        reset_action = QAction("Restaurar mezcla inicial", self)
        reset_action.triggered.connect(self._reset_design)
        file_menu.addAction(reset_action)

        file_menu.addSeparator()
        exit_action = QAction("Salir", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = self.menuBar().addMenu("Ayuda")
        about_action = QAction("Acerca de", self)
        about_action.triggered.connect(self._about)
        help_menu.addAction(about_action)

    def _return_to_suite(self) -> None:
        if self._on_return_to_suite is None:
            return
        self.hide()
        self._on_return_to_suite()

    def closeEvent(self, event) -> None:
        if self._on_return_to_suite is not None and self.isVisible():
            event.ignore()
            self._return_to_suite()
            return
        super().closeEvent(event)

    def _save_design(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar diseño",
            "mezcla_aci.json",
            "Diseño de mezcla (*.json)",
        )
        if filename:
            try:
                self.state.save_design(Path(filename))
            except Exception as error:
                QMessageBox.critical(self, "No se pudo exportar", str(error))

    def _load_design(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Importar diseño",
            "",
            "Diseño de mezcla (*.json)",
        )
        if filename:
            try:
                self.state.load_design(Path(filename))
                self.tabs.setCurrentWidget(self.laboratory_tab)
            except Exception as error:
                QMessageBox.critical(self, "No se pudo abrir", str(error))

    def _reset_design(self) -> None:
        answer = QMessageBox.question(
            self,
            "Restaurar mezcla",
            "¿Restaurar la mezcla académica inicial? Se perderán los cambios no guardados.",
        )
        if answer == QMessageBox.Yes:
            self.state.reset_design()

    def _open_production(self, production_id: int) -> None:
        self.production_page.select_production(production_id)
        self.tabs.setCurrentWidget(self.production_page)

    def navigate_to_activity(self, target) -> None:
        if target.activity_type == "production":
            self._open_production(int(target.source_id))
        elif target.activity_type == "shared_pie" and self.pie_page is not None:
            self.tabs.setCurrentWidget(self.pie_page)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            f"Acerca de {APP_NAME}",
            f"<b>{APP_NAME}</b><br>Versión {APP_VERSION}<br><br>"
            "Aplicación de escritorio para diseño por volúmenes absolutos, "
            "biblioteca de mezclas por grupos, registro de producción y trazabilidad de ensayos.<br><br>"
            "Desarrollada por Ing. Samuel Parariá — Derechos reservados.<br><br>"
            "Los resultados deben verificarse con los procedimientos de control de calidad y las especificaciones aplicables.",
        )
