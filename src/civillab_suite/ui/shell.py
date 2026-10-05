from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from civillab_suite.config import APP_NAME, APP_VERSION
from civillab_suite.data_portability import DataPortabilityError, DataPortabilityService
from civillab_suite.registry import ModuleDescriptor, ModuleRegistry, ModuleStatus
from civillab_suite.ui.styles import SHELL_STYLESHEET


class ModuleCard(QFrame):
    open_requested = Signal(str)

    def __init__(
        self,
        module: ModuleDescriptor,
        *,
        enabled: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.module = module
        self.setObjectName("ModuleCard")
        self.setProperty("moduleId", module.id)
        self.setMinimumWidth(280)
        self.setMaximumWidth(410)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 18)
        layout.setSpacing(12)

        logo = QLabel()
        logo.setObjectName("ModuleLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setMinimumHeight(230)
        logo.setAccessibleName(f"Logo oficial de {module.name}")
        pixmap = QPixmap(str(module.logo_path))
        if not pixmap.isNull():
            logo.setPixmap(
                pixmap.scaled(
                    260,
                    260,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            logo.setText("Recurso de identidad no disponible")

        heading = QHBoxLayout()
        name = QLabel(module.name)
        name.setObjectName("ModuleName")
        status = QLabel()
        if module.status is ModuleStatus.NOT_IMPLEMENTED:
            status.setText("PRÓXIMAMENTE")
            status.setObjectName("StatusSoon")
        elif enabled:
            status.setText("HABILITADO")
            status.setObjectName("StatusAvailable")
        else:
            status.setText("SIN LICENCIA")
            status.setObjectName("StatusSoon")
        heading.addWidget(name, 1)
        heading.addWidget(status, 0, Qt.AlignmentFlag.AlignRight)

        description = QLabel(module.description)
        description.setObjectName("ModuleDescription")
        description.setWordWrap(True)
        description.setMinimumHeight(44)

        button = QPushButton(
            "Abrir módulo" if enabled else "Módulo no disponible"
        )
        button.setObjectName("OpenModuleButton")
        button.setProperty("moduleId", module.id)
        button.setEnabled(enabled)
        if enabled:
            button.setStyleSheet(
                "QPushButton {"
                f"background-color: {module.accent_color};"
                f"border: 1px solid {module.accent_color};"
                "color: #07111f; border-radius: 10px; padding: 11px 16px;"
                "font-size: 13px; font-weight: 750;"
                "}"
                "QPushButton:hover { border-color: #ffffff; }"
                "QPushButton:pressed { padding-top: 12px; padding-bottom: 10px; }"
            )
        button.clicked.connect(lambda: self.open_requested.emit(module.id))

        layout.addWidget(logo)
        layout.addLayout(heading)
        layout.addWidget(description)
        layout.addStretch()
        layout.addWidget(button)

        self.logo_label = logo
        self.status_label = status
        self.open_button = button


class SuiteWindow(QMainWindow):
    module_requested = Signal(str)
    prepare_for_data_import = Signal()
    restart_required = Signal()

    def __init__(
        self,
        registry: ModuleRegistry,
        portability_service: DataPortabilityService | None = None,
    ):
        super().__init__()
        self.registry = registry
        self.cards: dict[str, ModuleCard] = {}
        self.portability_service = portability_service or DataPortabilityService()
        self.setObjectName("SuiteWindow")
        self.setWindowTitle(f"{APP_NAME} · v{APP_VERSION}")
        self.resize(1500, 920)
        self.setMinimumSize(1040, 720)
        self.setStyleSheet(SHELL_STYLESHEET)

        central = QWidget()
        central.setObjectName("SuiteCentral")
        root = QVBoxLayout(central)
        root.setContentsMargins(34, 28, 34, 24)
        root.setSpacing(22)

        hero = QFrame()
        hero.setObjectName("HeroPanel")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(30, 25, 30, 25)
        hero_layout.setSpacing(6)
        eyebrow = QLabel("PLATAFORMA INTEGRADA DE LABORATORIO")
        eyebrow.setObjectName("SuiteEyebrow")
        title = QLabel("CivilLab Suite")
        title.setObjectName("SuiteTitle")
        subtitle = QLabel(
            "Seleccione el entorno de trabajo. Los módulos comparten una sola sesión de aplicación."
        )
        subtitle.setObjectName("SuiteSubtitle")
        subtitle.setWordWrap(True)
        hero_layout.addWidget(eyebrow)
        hero_layout.addWidget(title)
        hero_layout.addWidget(subtitle)
        root.addWidget(hero)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        card_host = QWidget()
        card_host.setStyleSheet("background: transparent;")
        grid = QGridLayout(card_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(18)
        for column, module in enumerate(registry.all()):
            card = ModuleCard(module, enabled=registry.is_enabled(module.id))
            card.open_requested.connect(self.module_requested)
            self.cards[module.id] = card
            grid.addWidget(card, 0, column)
            grid.setColumnStretch(column, 1)
        scroll.setWidget(card_host)
        root.addWidget(scroll, 1)
        self.setCentralWidget(central)

        file_menu = self.menuBar().addMenu("Archivo")
        self.export_data_action = QAction("Exportar Datos Generales…", self)
        self.export_data_action.triggered.connect(self._export_general_data)
        file_menu.addAction(self.export_data_action)
        self.import_data_action = QAction("Importar Datos Generales…", self)
        self.import_data_action.triggered.connect(self._import_general_data)
        file_menu.addAction(self.import_data_action)
        self.new_environment_action = QAction("Nuevo entorno de datos…", self)
        self.new_environment_action.triggered.connect(self._new_environment)
        file_menu.addAction(self.new_environment_action)
        file_menu.addSeparator()
        exit_action = QAction("Salir de CivilLab Suite", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        self.statusBar().showMessage("Concretos y Prefabricados disponibles · Suelos en preparación")

    def _export_general_data(self) -> None:
        suggested = Path.home() / f"CivilLab-Datos-{datetime.now():%Y%m%d}.civillab"
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Exportar Datos Generales",
            str(suggested),
            "Paquete CivilLab (*.civillab)",
        )
        if not selected:
            return
        try:
            destination = self.portability_service.export_data(Path(selected))
        except (DataPortabilityError, OSError) as error:
            QMessageBox.critical(self, "No se pudieron exportar los datos", str(error))
            return
        QMessageBox.information(
            self,
            "Exportación completada",
            f"Los datos generales se guardaron en:\n{destination}",
        )

    def _import_general_data(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Importar Datos Generales",
            str(Path.home()),
            "Paquete CivilLab (*.civillab)",
        )
        if not selected:
            return
        package_path = Path(selected)
        try:
            summary = self.portability_service.inspect_package(package_path)
        except (DataPortabilityError, OSError) as error:
            QMessageBox.critical(self, "Paquete no válido", str(error))
            return

        answer = QMessageBox.warning(
            self,
            "Reemplazar datos de CivilLab Suite",
            "El paquete fue validado correctamente.\n\n"
            f"Creado: {summary.created_at}\n"
            f"Versión de origen: {summary.app_version}\n\n"
            "Los datos funcionales actuales serán reemplazados. Antes se creará "
            "automáticamente un respaldo .civillab. ¿Desea continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.prepare_for_data_import.emit()
        try:
            result = self.portability_service.import_data(package_path)
        except (DataPortabilityError, OSError) as error:
            QMessageBox.critical(self, "No se pudieron importar los datos", str(error))
            return
        QMessageBox.information(
            self,
            "Importación completada",
            "Los datos se restauraron correctamente. CivilLab Suite se cerrará para "
            "cargar el nuevo estado al volver a iniciarse.\n\n"
            f"Respaldo anterior:\n{result.backup_path}",
        )
        self.restart_required.emit()

    def _new_environment(self) -> None:
        answer = QMessageBox.warning(
            self, "Nuevo entorno de datos",
            "Los datos actuales serán apartados después de crear un respaldo .civillab. "
            "Podrá recuperarlos con Importar Datos Generales. ¿Crear una base vacía?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.prepare_for_data_import.emit()
        try:
            backup = self.portability_service.new_environment()
        except (DataPortabilityError, OSError, ValueError) as error:
            QMessageBox.critical(self, "No se pudo crear el entorno", str(error))
            return
        QMessageBox.information(self, "Entorno nuevo",
            f"La base nueva está lista. CivilLab se cerrará; vuelva a iniciarlo.\nRespaldo: {backup}")
        self.restart_required.emit()
