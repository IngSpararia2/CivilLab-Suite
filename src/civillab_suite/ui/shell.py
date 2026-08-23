from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from civillab_suite.config import APP_NAME, APP_VERSION
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

    def __init__(self, registry: ModuleRegistry):
        super().__init__()
        self.registry = registry
        self.cards: dict[str, ModuleCard] = {}
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
        exit_action = QAction("Salir de CivilLab Suite", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        self.statusBar().showMessage("Concretos y Prefabricados disponibles · Suelos en preparación")
