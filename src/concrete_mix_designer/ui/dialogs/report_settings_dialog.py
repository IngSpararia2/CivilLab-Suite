from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from concrete_mix_designer.services.report_preferences import (
    ReportPreferences,
    ReportPreferencesStore,
)


class ReportSettingsDialog(QDialog):
    def __init__(self, store: ReportPreferencesStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._preferences = store.load()
        self._pending_logo_source: Path | None = None
        self._remove_logo_requested = False

        self.setWindowTitle("Personalizar y exportar formato PDF")
        self.setMinimumWidth(680)

        intro = QLabel(
            "Configura la presentación del informe. El logo, el membrete y el pie de página "
            "se guardan localmente y se reutilizan en las próximas exportaciones."
        )
        intro.setWordWrap(True)
        intro.setObjectName("Subtitle")

        self.logo_preview = QLabel("Sin logo")
        self.logo_preview.setAlignment(Qt.AlignCenter)
        self.logo_preview.setFixedSize(190, 90)
        self.logo_preview.setStyleSheet(
            "background:white; border:1px solid #bcc9d6; border-radius:6px; padding:4px;"
        )

        self.logo_path = QLineEdit()
        self.logo_path.setReadOnly(True)
        choose_logo = QPushButton("Seleccionar logo")
        choose_logo.clicked.connect(self._choose_logo)
        remove_logo = QPushButton("Quitar logo")
        remove_logo.setObjectName("Secondary")
        remove_logo.clicked.connect(self._remove_logo)

        logo_actions = QHBoxLayout()
        logo_actions.addWidget(choose_logo)
        logo_actions.addWidget(remove_logo)
        logo_actions.addStretch()
        logo_controls = QWidget()
        logo_controls_layout = QVBoxLayout(logo_controls)
        logo_controls_layout.setContentsMargins(0, 0, 0, 0)
        logo_controls_layout.addWidget(self.logo_path)
        logo_controls_layout.addLayout(logo_actions)

        logo_row = QHBoxLayout()
        logo_row.addWidget(self.logo_preview)
        logo_row.addWidget(logo_controls, 1)
        logo_widget = QWidget()
        logo_widget.setLayout(logo_row)

        self.letterhead = QPlainTextEdit()
        self.letterhead.setPlaceholderText(
            "Ej.: PRECONCRETOS S.A.\nLaboratorio de control de calidad - Proyecto ..."
        )
        self.letterhead.setMaximumHeight(100)
        self.letterhead.setPlainText(self._preferences.letterhead_text)

        self.footer = QPlainTextEdit()
        self.footer.setPlaceholderText(
            "Ej.: Dirección, teléfono, correo, código del formato o información legal."
        )
        self.footer.setMaximumHeight(85)
        self.footer.setPlainText(self._preferences.footer_text)

        form = QFormLayout()
        form.addRow("Logo del informe:", logo_widget)
        form.addRow("Texto bajo el título (membrete/subtítulo):", self.letterhead)
        form.addRow("Texto del pie de página:", self.footer)

        note = QLabel(
            "El PDF tendrá dos páginas: una hoja técnica para laboratorio y una ficha para "
            "cliente que no muestra cantidades ni dosificaciones internas."
        )
        note.setWordWrap(True)
        note.setObjectName("Subtitle")

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        save_button = buttons.button(QDialogButtonBox.Save)
        save_button.setText("Guardar configuración y continuar")
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addSpacing(6)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

        self._set_logo_display(self._preferences.logo_path)

    @property
    def preferences(self) -> ReportPreferences:
        return self._preferences

    def _choose_logo(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar logo",
            "",
            "Imágenes (*.png *.jpg *.jpeg)",
        )
        if not filename:
            return
        self._pending_logo_source = Path(filename)
        self._remove_logo_requested = False
        self._set_logo_display(filename)

    def _remove_logo(self) -> None:
        self._pending_logo_source = None
        self._remove_logo_requested = True
        self._set_logo_display("")

    def _set_logo_display(self, path: str) -> None:
        self.logo_path.setText(path)
        if not path or not Path(path).exists():
            self.logo_preview.setPixmap(QPixmap())
            self.logo_preview.setText("Sin logo")
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.logo_preview.setPixmap(QPixmap())
            self.logo_preview.setText("Vista previa no disponible")
            return
        self.logo_preview.setText("")
        self.logo_preview.setPixmap(
            pixmap.scaled(
                176,
                76,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def _save_and_accept(self) -> None:
        try:
            logo_path = self._preferences.logo_path
            if self._remove_logo_requested:
                self.store.remove_logo()
                logo_path = ""
            elif self._pending_logo_source is not None:
                logo_path = self.store.import_logo(self._pending_logo_source)

            self._preferences = self.store.save(
                ReportPreferences(
                    logo_path=logo_path,
                    letterhead_text=self.letterhead.toPlainText(),
                    footer_text=self.footer.toPlainText(),
                )
            )
        except Exception as error:
            QMessageBox.critical(self, "No se pudo guardar la configuración", str(error))
            return
        self.accept()
