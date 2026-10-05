from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from concrete_mix_designer.services.app_state import AppState
from concrete_mix_designer.services.pdf_report import export_mix_report
from concrete_mix_designer.services.report_preferences import ReportPreferencesStore
from concrete_mix_designer.services.unit_conversion import beam_volume_l, cylinder_volume_l
from concrete_mix_designer.ui.dialogs.production_dialogs import ProductionDialog
from concrete_mix_designer.ui.dialogs.report_settings_dialog import ReportSettingsDialog

CYLINDER_PRESETS = [
    ("Cilindro 100 × 200 mm", (100.0, 200.0)),
    ("Cilindro 150 × 300 mm", (150.0, 300.0)),
]

BEAM_PRESETS = [
    ("Vigueta 100 × 100 × 400 mm", (100.0, 100.0, 400.0)),
    ("Vigueta 150 × 150 × 500 mm", (150.0, 150.0, 500.0)),
    ("Vigueta 150 × 150 × 600 mm", (150.0, 150.0, 600.0)),
]


class ResultsPage(QWidget):
    production_created = Signal(int)
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self._rows: list[dict[str, float | str]] = []
        self._selected_design = None
        self._selected_record = None
        self._specification = None
        self.report_preferences_store = ReportPreferencesStore()

        title = QLabel("Dosificación y registro de producción")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Selecciona un diseño guardado para calcular la amasada, registrar la producción y "
            "generar los archivos de entrega. Los cambios temporales del Laboratorio no se usan aquí."
        )
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)

        self.batch_spin = QDoubleSpinBox()
        self.batch_spin.setRange(0.001, 100.0)
        self.batch_spin.setDecimals(4)
        self.batch_spin.setSuffix(" m³")
        self.batch_spin.setValue(1.0)
        self.batch_spin.setKeyboardTracking(False)
        self.batch_spin.valueChanged.connect(self._refresh_dosage_table)

        self.design_combo = QComboBox()
        self.design_combo.setMinimumWidth(260)
        self.design_combo.currentIndexChanged.connect(self._selected_design_changed)

        register_production = QPushButton("Registrar producción")
        register_production.clicked.connect(self._register_production)
        export_csv = QPushButton("Exportar CSV")
        export_csv.setObjectName("Secondary")
        export_csv.clicked.connect(self._export_csv)
        export_pdf = QPushButton("Exportar formato PDF")
        export_pdf.clicked.connect(self._export_pdf)

        controls = QGridLayout()
        controls.addWidget(QLabel("Volumen de amasada:"), 0, 0)
        controls.addWidget(self.batch_spin, 0, 1)
        controls.addWidget(QLabel("Diseño guardado:"), 0, 2)
        controls.addWidget(self.design_combo, 0, 3)
        controls.setColumnStretch(3, 1)

        control_actions = QHBoxLayout()
        control_actions.addStretch()
        control_actions.addWidget(register_production)
        control_actions.addWidget(export_csv)
        control_actions.addWidget(export_pdf)
        controls.addLayout(control_actions, 1, 0, 1, 4)

        self.design_summary = QLabel("Selecciona un diseño guardado.")
        self.design_summary.setObjectName("Subtitle")
        self.design_summary.setWordWrap(True)
        self.moisture_warning = QLabel()
        self.moisture_warning.setWordWrap(True)
        self.moisture_warning.setStyleSheet(
            "background:#fff4e5; border:1px solid #f2c078; padding:8px; border-radius:6px;"
        )
        self.moisture_warning.hide()

        trial = QFrame()
        trial.setObjectName("Card")
        trial_layout = QGridLayout(trial)

        self.cylinder_preset = QComboBox()
        for label, dimensions in CYLINDER_PRESETS:
            self.cylinder_preset.addItem(label, dimensions)
        self.cylinder_count = QSpinBox()
        self.cylinder_count.setRange(0, 100)
        self.cylinder_count.setValue(6)

        self.beam_preset = QComboBox()
        for label, dimensions in BEAM_PRESETS:
            self.beam_preset.addItem(label, dimensions)
        self.beam_count = QSpinBox()
        self.beam_count.setRange(0, 100)
        self.beam_count.setValue(0)

        self.extra_l = QDoubleSpinBox()
        self.extra_l.setRange(0.0, 500.0)
        self.extra_l.setValue(12.0)
        self.extra_l.setSuffix(" L")
        self.waste_pct = QDoubleSpinBox()
        self.waste_pct.setRange(0.0, 200.0)
        self.waste_pct.setValue(20.0)
        self.waste_pct.setSuffix(" %")
        self.trial_result = QLabel("—")
        self.trial_result.setObjectName("Metric")
        self.trial_breakdown = QLabel(
            "Calcula el volumen mínimo para muestras, ensayos complementarios y reserva."
        )
        self.trial_breakdown.setObjectName("Subtitle")
        self.trial_breakdown.setWordWrap(True)

        calculate_trial = QPushButton("Calcular volumen de muestreo")
        calculate_trial.clicked.connect(self._calculate_trial)
        apply_trial = QPushButton("Usar como amasada")
        apply_trial.setObjectName("Secondary")
        apply_trial.clicked.connect(self._apply_trial)

        trial_layout.addWidget(QLabel("Cilindros:"), 0, 0)
        trial_layout.addWidget(self.cylinder_preset, 0, 1)
        trial_layout.addWidget(QLabel("Cantidad:"), 0, 2)
        trial_layout.addWidget(self.cylinder_count, 0, 3)
        trial_layout.addWidget(QLabel("Viguetas de flexión:"), 1, 0)
        trial_layout.addWidget(self.beam_preset, 1, 1)
        trial_layout.addWidget(QLabel("Cantidad:"), 1, 2)
        trial_layout.addWidget(self.beam_count, 1, 3)
        trial_layout.addWidget(QLabel("Concreto adicional:"), 2, 0)
        trial_layout.addWidget(self.extra_l, 2, 1)
        trial_layout.addWidget(QLabel("Pérdidas y reserva:"), 2, 2)
        trial_layout.addWidget(self.waste_pct, 2, 3)
        trial_layout.addWidget(calculate_trial, 3, 0)
        trial_layout.addWidget(self.trial_result, 3, 1, 1, 2)
        trial_layout.addWidget(apply_trial, 3, 3)
        trial_layout.addWidget(self.trial_breakdown, 4, 0, 1, 4)
        self._trial_m3 = 0.0

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "Material",
                "Unidad",
                "Diseño / m³",
                "Corregido / m³",
                "Aporte de agua",
                "Diseño / amasada",
                "Corregido / amasada",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 7):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )

        note = QLabel(
            "La corrección de humedad y las cantidades se calculan a partir de la copia guardada "
            "del diseño seleccionado."
        )
        note.setWordWrap(True)
        note.setObjectName("Subtitle")

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.addLayout(controls)
        card_layout.addWidget(self.design_summary)
        card_layout.addWidget(self.moisture_warning)
        from concrete_mix_designer.ui.moisture_widget import MoistureWidget
        self.moistures = MoistureWidget()
        self.moistures.changed.connect(self._refresh_dosage_table)
        card_layout.addWidget(self.moistures)
        card_layout.addWidget(self.table, 1)
        card_layout.addWidget(note)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(trial)
        layout.addWidget(card, 1)

        state.library_changed.connect(self.refresh_designs)
        state.productions_changed.connect(self.refresh_designs)
        self.refresh_designs()

    def refresh_designs(self) -> None:
        current = self.design_combo.currentData()
        preferred = current or self.state.current_saved_design_id
        self.design_combo.blockSignals(True)
        self.design_combo.clear()
        self.design_combo.addItem("Selecciona un diseño guardado…", None)
        for record in self.state.saved_designs:
            group = f"{record.group_name} · " if record.group_name else ""
            self.design_combo.addItem(f"{group}{record.name}", record.id)
        index = self.design_combo.findData(preferred)
        self.design_combo.setCurrentIndex(index if index >= 0 else 0)
        self.design_combo.blockSignals(False)
        self._selected_design_changed()

    def _selected_design_changed(self, *_args) -> None:
        design_id = self.design_combo.currentData()
        if design_id is None:
            self._selected_design = None
            self._selected_record = None
            self._specification = None
            self._rows = []
            self.table.setRowCount(0)
            self.moisture_warning.clear()
            self.moisture_warning.hide()
            self.design_summary.setText(
                "Selecciona un diseño guardado para habilitar producción y exportación."
            )
            return
        try:
            self._selected_record = self.state.laboratory_repository.get_design(int(design_id))
            self._selected_design = self.state.laboratory_repository.load_mix_design(int(design_id))
            self._specification = self.state.get_design_specification(int(design_id))
        except Exception as error:
            QMessageBox.critical(self, "No se pudo cargar el diseño", str(error))
            return
        self.moistures.set_design(self._selected_design)
        spec = self._specification
        strength = spec.primary_strength_mpa
        consistency = spec.consistency_value_mm
        self.design_summary.setText(
            f"Diseño productivo: {self._selected_record.name} · "
            f"Resistencia: {strength:.2f} MPa · " if strength is not None else f"Diseño productivo: {self._selected_record.name} · "
        )
        detail = []
        if consistency is not None:
            detail.append(f"Consistencia: {consistency:.0f} mm")
        if spec.nominal_max_size_mm is not None:
            detail.append(f"TMN: {spec.nominal_max_size_mm:g} mm")
        if detail:
            self.design_summary.setText(self.design_summary.text() + " · ".join(detail))
        self._refresh_dosage_table()

    def _refresh_dosage_table(self, *_args) -> None:
        if self._selected_design is None:
            self.table.setRowCount(0)
            self.moisture_warning.clear()
            self.moisture_warning.hide()
            return
        try:
            self._selected_design.batch_moistures = self.moistures.values()
            self._rows = self.state.engine.moisture_correction(self._selected_design)
        except ValueError as error:
            self._rows = []
            self.table.setRowCount(0)
            self.moisture_warning.setText(
                f"No se pudo calcular la corrección de humedad: {error}"
            )
            self.moisture_warning.show()
            return
        warning = next(
            (
                str(row.get("water_balance_warning", ""))
                for row in self._rows
                if row.get("water_balance_warning")
            ),
            "",
        )
        self.moisture_warning.setText(warning)
        self.moisture_warning.setVisible(bool(warning))
        self.table.setRowCount(len(self._rows))
        factor = self.batch_spin.value()
        for row_index, row in enumerate(self._rows):
            unit = str(row["unit"])
            design = float(row["design_quantity"])
            corrected = float(row["corrected_quantity"])
            contribution = float(row["water_contribution"])
            values = [
                str(row["name"]),
                unit,
                f"{design:.3f}",
                f"{corrected:.3f}",
                f"{contribution:+.3f} kg",
                f"{design * factor:.3f}",
                f"{corrected * factor:.3f}",
            ]
            for column, value in enumerate(values):
                self.table.setItem(row_index, column, QTableWidgetItem(value))

    def _calculate_trial(self) -> None:
        cylinder_diameter, cylinder_height = self.cylinder_preset.currentData()
        beam_width, beam_depth, beam_length = self.beam_preset.currentData()
        one_cylinder_l = cylinder_volume_l(cylinder_diameter, cylinder_height)
        one_beam_l = beam_volume_l(beam_width, beam_depth, beam_length)
        cylinders_l = one_cylinder_l * self.cylinder_count.value()
        beams_l = one_beam_l * self.beam_count.value()
        net_l = cylinders_l + beams_l + self.extra_l.value()
        total_l = net_l * (1.0 + self.waste_pct.value() / 100.0)
        self._trial_m3 = total_l / 1000.0
        self.trial_result.setText(f"{total_l:.2f} L · {self._trial_m3:.4f} m³")
        self.trial_breakdown.setText(
            f"Cilindros: {cylinders_l:.2f} L · Viguetas: {beams_l:.2f} L · "
            f"Adicional: {self.extra_l.value():.2f} L · Neto: {net_l:.2f} L."
        )

    def _apply_trial(self) -> None:
        if self._trial_m3 <= 0:
            self._calculate_trial()
        self.batch_spin.setValue(self._trial_m3)

    def _require_saved_design(self) -> bool:
        if self._selected_record is None or self._selected_design is None:
            QMessageBox.information(
                self,
                "Selecciona un diseño",
                "Selecciona un diseño guardado antes de continuar.",
            )
            return False
        return True

    def _register_production(self) -> None:
        if not self._require_saved_design():
            return
        dialog = ProductionDialog(
            [self._selected_record],
            selected_design_id=self._selected_record.id,
            initial_batch_volume_m3=self.batch_spin.value(),
            lock_design=True,
            initial_moistures=self.moistures.values(),
            parent=self,
        )
        if dialog.exec():
            try:
                production = self.state.create_production(**dialog.values)
                self.production_created.emit(production.id)
            except Exception as error:
                QMessageBox.critical(self, "No se pudo registrar", str(error))

    def _export_csv(self) -> None:
        if not self._require_saved_design():
            return
        default_name = f"dosificacion_{self._selected_record.name}.csv".replace(" ", "_")
        filename, _ = QFileDialog.getSaveFileName(
            self, "Exportar dosificación", default_name, "CSV (*.csv)"
        )
        if not filename:
            return
        factor = self.batch_spin.value()
        with Path(filename).open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(
                [
                    "Diseño guardado",
                    self._selected_record.name,
                    "Volumen m3",
                    f"{factor:.4f}",
                ]
            )
            warning = next(
                (
                    str(row.get("water_balance_warning", ""))
                    for row in self._rows
                    if row.get("water_balance_warning")
                ),
                "",
            )
            if warning:
                writer.writerow(["Advertencia de humedad", warning])
            writer.writerow(
                [
                    "Material",
                    "Unidad",
                    "Diseño por m3",
                    "Corregido por m3",
                    "Aporte de agua kg",
                    "Diseño por amasada",
                    "Corregido por amasada",
                    "Absorción % OD",
                    "Humedad actual % OD",
                    "Base de diseño",
                ]
            )
            for row in self._rows:
                design = float(row["design_quantity"])
                corrected = float(row["corrected_quantity"])
                writer.writerow(
                    [
                        row["name"],
                        row["unit"],
                        f"{design:.3f}",
                        f"{corrected:.3f}",
                        f"{float(row['water_contribution']):+.3f}",
                        f"{design * factor:.3f}",
                        f"{corrected * factor:.3f}",
                        row.get("absorption_pct", ""),
                        row.get("moisture_pct", ""),
                        row.get("mass_basis", ""),
                    ]
                )
        self.state.message.emit("Dosificación CSV exportada.")

    def _export_pdf(self) -> None:
        if not self._require_saved_design():
            return
        settings_dialog = ReportSettingsDialog(self.report_preferences_store, self)
        if not settings_dialog.exec():
            return
        safe_name = "_".join(self._selected_record.name.split())[:60]
        default_name = f"reporte_{safe_name}_{datetime.now():%Y%m%d_%H%M%S}.pdf"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Exportar formato profesional", default_name, "PDF (*.pdf)"
        )
        if not filename:
            return
        try:
            output_path = export_mix_report(
                Path(filename),
                self._selected_design,
                self._rows,
                self.batch_spin.value(),
                preferences=settings_dialog.preferences,
                statistics=self.state.laboratory_repository.design_statistics(
                    self._selected_record.id
                ),
                design_name=self._selected_record.name,
                group_name=self._selected_record.group_name,
                description=self._selected_record.description,
                specification=self._specification,
            )
        except Exception as error:
            QMessageBox.critical(self, "No se pudo exportar el PDF", str(error))
            return
        self.state.message.emit(f"Formato PDF exportado como {output_path.name}.")
