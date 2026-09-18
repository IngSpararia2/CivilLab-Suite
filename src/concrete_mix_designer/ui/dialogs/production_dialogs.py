from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from civillab_suite.ui.shared_controls import ensure_table_row_height
from concrete_mix_designer.data.laboratory_repository import LaboratoryRepository
from concrete_mix_designer.domain.laboratory_models import (
    CompressionResultRecord,
    FlexuralResultRecord,
    FreshTestRecord,
    FreshTestType,
    SavedDesignRecord,
    SpecimenRecord,
    SpecimenType,
)
from concrete_mix_designer.services.unit_conversion import length_to_mm, mm_to_length

DEFAULT_AGES = (1, 3, 7, 14, 28, 56)


def _date_time_value(widget: QDateTimeEdit) -> datetime:
    value = widget.dateTime().toPython()
    return value.astimezone() if value.tzinfo is None else value


def _optional_spin(minimum: float, maximum: float, decimals: int = 2) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSpecialValueText("—")
    spin.setValue(minimum)
    return spin


def _optional_value(spin: QDoubleSpinBox) -> float | None:
    return None if spin.value() == spin.minimum() else spin.value()


class ScheduleTable(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            ["Edad objetivo (días)", "Cilindros", "Viguetas"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        add_age = QPushButton("Añadir edad personalizada")
        add_age.setObjectName("Secondary")
        add_age.clicked.connect(self._add_custom_age)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
        layout.addWidget(add_age)
        for age in DEFAULT_AGES:
            self.add_age(float(age))

    def add_age(self, age: float) -> None:
        existing = {
            float(self.table.item(row, 0).data(Qt.UserRole))
            for row in range(self.table.rowCount())
            if self.table.item(row, 0) is not None
        }
        if age in existing:
            return
        row = self.table.rowCount()
        self.table.insertRow(row)
        age_item = QTableWidgetItem(f"{age:g}")
        age_item.setData(Qt.UserRole, age)
        self.table.setItem(row, 0, age_item)
        for column in (1, 2):
            count = QSpinBox()
            count.setRange(0, 50)
            count.setValue(0)
            self.table.setCellWidget(row, column, count)
        ensure_table_row_height(self.table, row)
        self.table.sortItems(0)

    def _add_custom_age(self) -> None:
        age, accepted = QInputDialog.getDouble(
            self,
            "Edad personalizada",
            "Edad objetivo en días:",
            2.0,
            0.0,
            3650.0,
            2,
        )
        if accepted:
            self.add_age(age)

    def schedules(self) -> list[tuple[SpecimenType, float, int]]:
        schedules: list[tuple[SpecimenType, float, int]] = []
        for row in range(self.table.rowCount()):
            age_item = self.table.item(row, 0)
            if age_item is None:
                continue
            age = float(age_item.data(Qt.UserRole))
            cylinder_count = self.table.cellWidget(row, 1)
            beam_count = self.table.cellWidget(row, 2)
            if isinstance(cylinder_count, QSpinBox) and cylinder_count.value() > 0:
                schedules.append((SpecimenType.CYLINDER, age, cylinder_count.value()))
            if isinstance(beam_count, QSpinBox) and beam_count.value() > 0:
                schedules.append((SpecimenType.BEAM, age, beam_count.value()))
        return schedules


class ProductionDialog(QDialog):
    def __init__(
        self,
        designs: list[SavedDesignRecord],
        *,
        selected_design_id: int | None = None,
        initial_batch_volume_m3: float = 1.0,
        lock_design: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Registrar producción")
        self.resize(700, 680)

        self.design_combo = QComboBox()
        for design in designs:
            group_text = f"{design.group_name} · " if design.group_name else ""
            self.design_combo.addItem(f"{group_text}{design.name}", design.id)
        if selected_design_id is not None:
            index = self.design_combo.findData(selected_design_id)
            if index >= 0:
                self.design_combo.setCurrentIndex(index)
        self.design_combo.setEnabled(not lock_design)

        self.produced_at = QDateTimeEdit(QDateTime.currentDateTime())
        self.produced_at.setCalendarPopup(True)
        self.produced_at.setDisplayFormat("yyyy-MM-dd HH:mm")

        self.batch_code = QLineEdit()
        self.batch_code.setPlaceholderText("Se genera automáticamente si se deja vacío")

        self.batch_volume = QDoubleSpinBox()
        self.batch_volume.setRange(0.001, 10000.0)
        self.batch_volume.setDecimals(4)
        self.batch_volume.setValue(float(initial_batch_volume_m3))
        self.batch_volume.setSuffix(" m³")

        self.notes = QPlainTextEdit()
        self.notes.setMaximumHeight(90)
        self.notes.setPlaceholderText("Lote de materiales, operador, ubicación, incidencias u observaciones.")

        form = QFormLayout()
        form.addRow("Diseño guardado:*", self.design_combo)
        form.addRow("Fecha y hora de fabricación:*", self.produced_at)
        form.addRow("Código o lote:", self.batch_code)
        form.addRow("Volumen producido:*", self.batch_volume)
        form.addRow("Observaciones:", self.notes)

        schedule_group = QGroupBox("Muestras separadas y edades programadas")
        self.schedule_table = ScheduleTable()
        schedule_layout = QVBoxLayout(schedule_group)
        schedule_layout.addWidget(
            QLabel(
                "Registra cuántos cilindros y viguetas se separan para cada edad. "
                "La fecha prevista se calcula desde la fecha de producción."
            )
        )
        schedule_layout.addWidget(self.schedule_table)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(schedule_group, 1)
        layout.addWidget(buttons)

    def accept(self) -> None:
        if self.design_combo.currentData() is None:
            QMessageBox.warning(self, "Diseño requerido", "Guarda y selecciona un diseño primero.")
            return
        super().accept()

    @property
    def values(self) -> dict[str, object]:
        return {
            "design_id": int(self.design_combo.currentData()),
            "produced_at": _date_time_value(self.produced_at),
            "batch_code": self.batch_code.text().strip(),
            "batch_volume_m3": self.batch_volume.value(),
            "notes": self.notes.toPlainText().strip(),
            "schedules": self.schedule_table.schedules(),
        }


class AddSpecimensDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Añadir muestras programadas")

        self.type_combo = QComboBox()
        self.type_combo.addItem("Cilindros para compresión", SpecimenType.CYLINDER)
        self.type_combo.addItem("Viguetas para módulo de rotura", SpecimenType.BEAM)
        self.age = QDoubleSpinBox()
        self.age.setRange(0.0, 3650.0)
        self.age.setDecimals(2)
        self.age.setValue(28.0)
        self.age.setSuffix(" días")
        self.count = QSpinBox()
        self.count.setRange(1, 100)
        self.count.setValue(3)

        form = QFormLayout()
        form.addRow("Tipo:", self.type_combo)
        form.addRow("Edad objetivo:", self.age)
        form.addRow("Cantidad:", self.count)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @property
    def values(self) -> dict[str, object]:
        return {
            "specimen_type": SpecimenType(self.type_combo.currentData()),
            "target_age_days": self.age.value(),
            "count": self.count.value(),
        }


class FreshTestDialog(QDialog):
    def __init__(
        self,
        *,
        produced_at: datetime,
        existing: FreshTestRecord | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.produced_at_value = produced_at
        self.existing = existing
        self.setWindowTitle(
            "Editar dato de concreto fresco"
            if existing is not None
            else "Añadir ensayo de concreto fresco"
        )
        self.setMinimumWidth(520)

        self.type_combo = QComboBox()
        self.type_combo.addItem("Asentamiento", FreshTestType.SLUMP)
        self.type_combo.addItem("Esparcimiento", FreshTestType.SPREAD)
        self.type_combo.currentIndexChanged.connect(self._update_visibility)

        self.measured_at = QDateTimeEdit(QDateTime.currentDateTime())
        self.measured_at.setCalendarPopup(True)
        self.measured_at.setDisplayFormat("yyyy-MM-dd HH:mm")

        self.slump = _optional_spin(-0.01, 12.0, 2)
        self.slump.setSingleStep(0.25)
        self.slump.setSuffix(" in")
        self.slump_unit = QComboBox()
        self.slump_unit.addItem("Pulgadas", "in")
        self.slump_unit.addItem("Milímetros", "mm")
        self.slump_unit.currentIndexChanged.connect(self._change_slump_unit)
        slump_box = QHBoxLayout()
        slump_box.setContentsMargins(0, 0, 0, 0)
        slump_box.addWidget(self.slump)
        slump_box.addWidget(self.slump_unit)
        self.slump_widget = QWidget()
        self.slump_widget.setLayout(slump_box)
        self.spread_d1 = _optional_spin(-1.0, 2000.0, 1)
        self.spread_d1.setSuffix(" mm")
        self.spread_d2 = _optional_spin(-1.0, 2000.0, 1)
        self.spread_d2.setSuffix(" mm")
        self.temperature = _optional_spin(-100.0, 100.0, 1)
        self.temperature.setSuffix(" °C")
        self.air_content = _optional_spin(-1.0, 30.0, 2)
        self.air_content.setSuffix(" %")
        self.unit_weight = _optional_spin(-1.0, 4000.0, 1)
        self.unit_weight.setSuffix(" kg/m³")
        self.notes = QPlainTextEdit()
        self.notes.setMaximumHeight(90)

        form = QFormLayout()
        form.addRow("Tipo de ensayo:*", self.type_combo)
        form.addRow("Fecha y hora de lectura:*", self.measured_at)
        self.slump_label = QLabel("Asentamiento:*")
        form.addRow(self.slump_label, self.slump_widget)
        self.spread1_label = QLabel("Diámetro 1:*")
        form.addRow(self.spread1_label, self.spread_d1)
        self.spread2_label = QLabel("Diámetro 2:")
        form.addRow(self.spread2_label, self.spread_d2)
        form.addRow("Temperatura del concreto:", self.temperature)
        form.addRow("Contenido de aire:", self.air_content)
        form.addRow("Masa unitaria:", self.unit_weight)
        form.addRow("Observaciones:", self.notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        if existing is not None:
            self._load_existing(existing)
        self._update_visibility()

    @staticmethod
    def _set_optional(widget: QDoubleSpinBox, value: float | None) -> None:
        widget.setValue(widget.minimum() if value is None else value)

    def _load_existing(self, existing: FreshTestRecord) -> None:
        for index in range(self.type_combo.count()):
            if FreshTestType(self.type_combo.itemData(index)) == existing.test_type:
                self.type_combo.setCurrentIndex(index)
                break
        self.measured_at.setDateTime(QDateTime(existing.measured_at))
        if existing.slump_mm is not None:
            self.slump_unit.setCurrentIndex(self.slump_unit.findData("in"))
            self.slump.setValue(mm_to_length(existing.slump_mm, "in"))
        self._set_optional(self.spread_d1, existing.spread_d1_mm)
        self._set_optional(self.spread_d2, existing.spread_d2_mm)
        self._set_optional(self.temperature, existing.concrete_temperature_c)
        self._set_optional(self.air_content, existing.air_content_pct)
        self._set_optional(self.unit_weight, existing.unit_weight_kg_m3)
        self.notes.setPlainText(existing.notes)

    def _update_visibility(self) -> None:
        slump_mode = FreshTestType(self.type_combo.currentData()) == FreshTestType.SLUMP
        self.slump_label.setVisible(slump_mode)
        self.slump_widget.setVisible(slump_mode)
        self.spread1_label.setVisible(not slump_mode)
        self.spread_d1.setVisible(not slump_mode)
        self.spread2_label.setVisible(not slump_mode)
        self.spread_d2.setVisible(not slump_mode)

    def _change_slump_unit(self) -> None:
        current = _optional_value(self.slump)
        old_unit = "in" if self.slump.suffix().strip() == "in" else "mm"
        value_mm = length_to_mm(current, old_unit) if current is not None else None
        new_unit = str(self.slump_unit.currentData())
        self.slump.blockSignals(True)
        if new_unit == "in":
            self.slump.setRange(-0.01, 12.0)
            self.slump.setDecimals(2)
            self.slump.setSingleStep(0.25)
            self.slump.setSuffix(" in")
        else:
            self.slump.setRange(-1.0, 300.0)
            self.slump.setDecimals(1)
            self.slump.setSingleStep(5.0)
            self.slump.setSuffix(" mm")
        if value_mm is None:
            self.slump.setValue(self.slump.minimum())
        else:
            self.slump.setValue(mm_to_length(value_mm, new_unit))
        self.slump.blockSignals(False)

    def accept(self) -> None:
        if FreshTestType(self.type_combo.currentData()) == FreshTestType.SLUMP and _optional_value(self.slump) is None:
            QMessageBox.warning(self, "Dato requerido", "Registra el asentamiento.")
            return
        if FreshTestType(self.type_combo.currentData()) == FreshTestType.SPREAD and _optional_value(self.spread_d1) is None:
            QMessageBox.warning(self, "Dato requerido", "Registra al menos el primer diámetro.")
            return
        super().accept()

    @property
    def values(self) -> dict[str, object]:
        slump_value = _optional_value(self.slump)
        slump_mm = (
            length_to_mm(slump_value, str(self.slump_unit.currentData()))
            if slump_value is not None
            else None
        )
        return {
            "test_type": FreshTestType(self.type_combo.currentData()),
            "measured_at": _date_time_value(self.measured_at),
            "slump_mm": slump_mm,
            "spread_d1_mm": _optional_value(self.spread_d1),
            "spread_d2_mm": _optional_value(self.spread_d2),
            "concrete_temperature_c": _optional_value(self.temperature),
            "air_content_pct": _optional_value(self.air_content),
            "unit_weight_kg_m3": _optional_value(self.unit_weight),
            "notes": self.notes.toPlainText().strip(),
        }


class CompressionResultDialog(QDialog):
    def __init__(
        self,
        repository: LaboratoryRepository,
        specimen: SpecimenRecord,
        existing: CompressionResultRecord | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.repository = repository
        self.setWindowTitle(f"Resultado de compresión · {specimen.specimen_code}")
        self.setMinimumWidth(520)

        self.tested_at = QDateTimeEdit(QDateTime.currentDateTime())
        self.tested_at.setCalendarPopup(True)
        self.tested_at.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.diameter = QDoubleSpinBox()
        self.diameter.setRange(1.0, 1000.0)
        self.diameter.setDecimals(2)
        self.diameter.setValue(100.0)
        self.diameter.setSuffix(" mm")
        self.height = _optional_spin(-1.0, 2000.0, 2)
        self.height.setSuffix(" mm")
        self.mass = _optional_spin(-1.0, 1000.0, 3)
        self.mass.setSuffix(" kg")
        self.load = QDoubleSpinBox()
        self.load.setRange(0.0, 100000.0)
        self.load.setDecimals(3)
        self.load.setSuffix(" kN")
        self.strength = QDoubleSpinBox()
        self.strength.setRange(0.0, 1000.0)
        self.strength.setDecimals(3)
        self.strength.setSuffix(" MPa")
        self.failure = QLineEdit()
        self.machine = QLineEdit()
        self.technician = QLineEdit()
        self.notes = QPlainTextEdit()
        self.notes.setMaximumHeight(90)

        self.load.valueChanged.connect(self._recalculate)
        self.diameter.valueChanged.connect(self._recalculate)

        form = QFormLayout()
        form.addRow("Fecha y hora del ensayo:*", self.tested_at)
        form.addRow("Diámetro promedio:*", self.diameter)
        form.addRow("Altura:", self.height)
        form.addRow("Masa:", self.mass)
        form.addRow("Carga máxima:*", self.load)
        form.addRow("Resistencia a compresión:*", self.strength)
        form.addRow("Tipo de falla:", self.failure)
        form.addRow("Máquina:", self.machine)
        form.addRow("Técnico:", self.technician)
        form.addRow("Observaciones:", self.notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        if existing:
            self.tested_at.setDateTime(QDateTime(existing.tested_at))
            self.diameter.setValue(existing.diameter_mm)
            self.height.setValue(existing.height_mm if existing.height_mm is not None else -1.0)
            self.mass.setValue(existing.mass_kg if existing.mass_kg is not None else -1.0)
            self.load.setValue(existing.max_load_kn)
            self.strength.setValue(existing.strength_mpa)
            self.failure.setText(existing.failure_type)
            self.machine.setText(existing.machine)
            self.technician.setText(existing.technician)
            self.notes.setPlainText(existing.notes)

    def _recalculate(self) -> None:
        self.strength.setValue(
            self.repository.calculate_compressive_strength(
                self.load.value(), self.diameter.value()
            )
        )

    @property
    def values(self) -> dict[str, object]:
        return {
            "tested_at": _date_time_value(self.tested_at),
            "diameter_mm": self.diameter.value(),
            "height_mm": _optional_value(self.height),
            "mass_kg": _optional_value(self.mass),
            "max_load_kn": self.load.value(),
            "strength_mpa": self.strength.value(),
            "failure_type": self.failure.text().strip(),
            "machine": self.machine.text().strip(),
            "technician": self.technician.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }


class FlexuralResultDialog(QDialog):
    def __init__(
        self,
        repository: LaboratoryRepository,
        specimen: SpecimenRecord,
        existing: FlexuralResultRecord | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.repository = repository
        self.setWindowTitle(f"Módulo de rotura · {specimen.specimen_code}")
        self.setMinimumWidth(520)

        self.tested_at = QDateTimeEdit(QDateTime.currentDateTime())
        self.tested_at.setCalendarPopup(True)
        self.tested_at.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.width = QDoubleSpinBox()
        self.width.setRange(1.0, 2000.0)
        self.width.setDecimals(2)
        self.width.setValue(150.0)
        self.width.setSuffix(" mm")
        self.depth = QDoubleSpinBox()
        self.depth.setRange(1.0, 2000.0)
        self.depth.setDecimals(2)
        self.depth.setValue(150.0)
        self.depth.setSuffix(" mm")
        self.span = QDoubleSpinBox()
        self.span.setRange(1.0, 10000.0)
        self.span.setDecimals(2)
        self.span.setValue(450.0)
        self.span.setSuffix(" mm")
        self.fracture_distance = _optional_spin(-1.0, 10000.0, 2)
        self.fracture_distance.setSuffix(" mm")
        self.load = QDoubleSpinBox()
        self.load.setRange(0.0, 100000.0)
        self.load.setDecimals(3)
        self.load.setSuffix(" kN")
        self.modulus = QDoubleSpinBox()
        self.modulus.setRange(0.0, 1000.0)
        self.modulus.setDecimals(3)
        self.modulus.setSuffix(" MPa")
        self.failure = QLineEdit()
        self.machine = QLineEdit()
        self.technician = QLineEdit()
        self.notes = QPlainTextEdit()
        self.notes.setMaximumHeight(90)
        self.calculation_note = QLabel()
        self.calculation_note.setWordWrap(True)
        self.calculation_note.setStyleSheet("color:#b42318;")

        for widget in (
            self.load,
            self.width,
            self.depth,
            self.span,
            self.fracture_distance,
        ):
            widget.valueChanged.connect(self._recalculate)

        form = QFormLayout()
        form.addRow("Fecha y hora del ensayo:*", self.tested_at)
        form.addRow("Ancho promedio:*", self.width)
        form.addRow("Profundidad promedio:*", self.depth)
        form.addRow("Luz entre apoyos:*", self.span)
        form.addRow(
            "Fractura al apoyo más cercano:", self.fracture_distance
        )
        form.addRow("Carga máxima:*", self.load)
        form.addRow("Módulo de rotura:*", self.modulus)
        form.addRow("", self.calculation_note)
        form.addRow("Tipo de falla:", self.failure)
        form.addRow("Máquina:", self.machine)
        form.addRow("Técnico:", self.technician)
        form.addRow("Observaciones:", self.notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        if existing:
            self.tested_at.setDateTime(QDateTime(existing.tested_at))
            self.width.setValue(existing.width_mm)
            self.depth.setValue(existing.depth_mm)
            self.span.setValue(existing.span_mm)
            self.fracture_distance.setValue(
                existing.fracture_distance_mm
                if existing.fracture_distance_mm is not None
                else -1.0
            )
            self.load.setValue(existing.max_load_kn)
            self.modulus.setValue(existing.modulus_of_rupture_mpa)
            self.failure.setText(existing.failure_type)
            self.machine.setText(existing.machine)
            self.technician.setText(existing.technician)
            self.notes.setPlainText(existing.notes)

    def _recalculate(self) -> None:
        try:
            result = self.repository.calculate_modulus_of_rupture(
                self.load.value(),
                self.span.value(),
                self.width.value(),
                self.depth.value(),
                _optional_value(self.fracture_distance),
            )
        except ValueError as error:
            self.modulus.setValue(0.0)
            self.calculation_note.setText(str(error))
            return
        self.calculation_note.clear()
        self.modulus.setValue(result)

    def _accept(self) -> None:
        try:
            self.repository.calculate_modulus_of_rupture(
                self.load.value(),
                self.span.value(),
                self.width.value(),
                self.depth.value(),
                _optional_value(self.fracture_distance),
            )
        except ValueError as error:
            QMessageBox.warning(self, "Resultado no válido", str(error))
            return
        self.accept()

    @property
    def values(self) -> dict[str, object]:
        return {
            "tested_at": _date_time_value(self.tested_at),
            "width_mm": self.width.value(),
            "depth_mm": self.depth.value(),
            "span_mm": self.span.value(),
            "fracture_distance_mm": _optional_value(self.fracture_distance),
            "max_load_kn": self.load.value(),
            "modulus_of_rupture_mpa": self.modulus.value(),
            "failure_type": self.failure.text().strip(),
            "machine": self.machine.text().strip(),
            "technician": self.technician.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }
