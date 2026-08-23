from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from concrete_mix_designer.domain.aci_seed import AciSuggestion
from concrete_mix_designer.services.app_state import AppState
from concrete_mix_designer.services.unit_conversion import (
    PRESSURE_UNIT_LABELS,
    length_to_mm,
    mm_to_length,
    mpa_to_pressure,
    pressure_to_mpa,
)

NMS_OPTIONS = [
    (9.5, '3/8"'),
    (12.5, '1/2"'),
    (19.0, '3/4"'),
    (25.0, '1"'),
    (37.5, '1 1/2"'),
    (50.0, '2"'),
    (75.0, '3"'),
]


class DashboardPage(QWidget):
    """Initial design settings.

    Values are always stored internally in MPa and millimetres. Unit selectors
    only change the values presented to the operator.
    """

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self._suggestion: AciSuggestion | None = None
        self._refreshing = False

        title = QLabel("Configuración inicial")
        title.setObjectName("Title")
        subtitle = QLabel("Define parámetros de desempeño y genera un punto de partida académico.")
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)

        self.fc_spin = self._spin(10.0, 100.0, 1, " MPa")
        self.fc_unit = QComboBox()
        self.fc_unit.addItem("Megapascales (MPa)", "mpa")
        self.fc_unit.addItem("Libras por pulgada cuadrada (psi)", "psi")
        self.fc_unit.addItem("Kilogramo-fuerza por cm² (kgf/cm²)", "kgf_cm2")
        self.fc_unit.currentIndexChanged.connect(self._change_fc_unit)
        fc_widget = self._paired_widget(self.fc_spin, self.fc_unit)

        self.slump_spin = self._spin(0.0, 12.0, 2, " in")
        self.slump_spin.setSingleStep(0.25)
        self.slump_unit = QComboBox()
        self.slump_unit.addItem("Pulgadas", "in")
        self.slump_unit.addItem("Milímetros", "mm")
        self.slump_unit.currentIndexChanged.connect(self._change_slump_unit)
        slump_widget = self._paired_widget(self.slump_spin, self.slump_unit)

        self.nms_combo = QComboBox()
        for mm, sieve in NMS_OPTIONS:
            self.nms_combo.addItem(f"{mm:g} mm · tamiz {sieve}", mm)
        self.air_entrained_check = QCheckBox("Con aire incluido")

        form = QFormLayout()
        form.addRow("Resistencia esperada f'c:", fc_widget)
        form.addRow("Asentamiento deseado:", slump_widget)
        form.addRow("Tamaño máximo nominal:", self.nms_combo)
        form.addRow("Exposición:", self.air_entrained_check)

        suggest_button = QPushButton("Calcular sugerencia inicial")
        suggest_button.clicked.connect(self._calculate_suggestion)
        self.apply_button = QPushButton("Aplicar al laboratorio")
        self.apply_button.setObjectName("Secondary")
        self.apply_button.clicked.connect(self._apply_suggestion)
        self.apply_button.setEnabled(False)
        button_row = QHBoxLayout()
        button_row.addWidget(suggest_button)
        button_row.addWidget(self.apply_button)
        button_row.addStretch()

        config_card = QFrame()
        config_card.setObjectName("Card")
        config_layout = QVBoxLayout(config_card)
        config_layout.addLayout(form)
        config_layout.addLayout(button_row)

        self.water_value = QLabel("—")
        self.water_value.setObjectName("Metric")
        self.ratio_value = QLabel("—")
        self.ratio_value.setObjectName("Metric")
        self.air_value = QLabel("—")
        self.air_value.setObjectName("Metric")
        self.note_label = QLabel("La sugerencia es un valor de arranque; la mezcla final requiere ensayos.")
        self.note_label.setWordWrap(True)
        self.note_label.setObjectName("Subtitle")

        result_card = QFrame()
        result_card.setObjectName("Card")
        result_layout = QVBoxLayout(result_card)
        result_layout.addWidget(QLabel("Sugerencia inicial"))
        metrics = QHBoxLayout()
        metrics.addLayout(self._metric("Agua", self.water_value))
        metrics.addLayout(self._metric("Relación a/mc", self.ratio_value))
        metrics.addLayout(self._metric("Aire", self.air_value))
        result_layout.addLayout(metrics)
        result_layout.addWidget(self.note_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(10)
        layout.addWidget(config_card)
        layout.addWidget(result_card)
        layout.addStretch()

        state.design_changed.connect(self.refresh)
        self.refresh()

    @staticmethod
    def _spin(minimum: float, maximum: float, decimals: int, suffix: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSuffix(suffix)
        spin.setSingleStep(1.0)
        spin.setKeyboardTracking(False)
        return spin

    @staticmethod
    def _paired_widget(value_widget: QWidget, unit_widget: QWidget) -> QWidget:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(value_widget)
        layout.addWidget(unit_widget)
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    @staticmethod
    def _metric(label: str, value_widget: QLabel) -> QVBoxLayout:
        layout = QVBoxLayout()
        caption = QLabel(label)
        caption.setAlignment(Qt.AlignCenter)
        value_widget.setAlignment(Qt.AlignCenter)
        layout.addWidget(caption)
        layout.addWidget(value_widget)
        return layout

    def _fc_mpa(self) -> float:
        return pressure_to_mpa(self.fc_spin.value(), str(self.fc_unit.currentData()))

    def _slump_mm(self) -> float:
        return length_to_mm(self.slump_spin.value(), str(self.slump_unit.currentData()))

    def _change_fc_unit(self) -> None:
        if self._refreshing:
            return
        old_suffix = self.fc_spin.suffix().strip()
        old_unit = next(
            (key for key, label in PRESSURE_UNIT_LABELS.items() if label == old_suffix),
            "mpa",
        )
        value_mpa = pressure_to_mpa(self.fc_spin.value(), old_unit)
        new_unit = str(self.fc_unit.currentData())
        self.fc_spin.blockSignals(True)
        if new_unit == "psi":
            self.fc_spin.setRange(1000.0, 15000.0)
            self.fc_spin.setDecimals(0)
            self.fc_spin.setSingleStep(100.0)
        elif new_unit == "kgf_cm2":
            self.fc_spin.setRange(100.0, 1100.0)
            self.fc_spin.setDecimals(1)
            self.fc_spin.setSingleStep(5.0)
        else:
            self.fc_spin.setRange(10.0, 100.0)
            self.fc_spin.setDecimals(1)
            self.fc_spin.setSingleStep(1.0)
        self.fc_spin.setSuffix(f" {PRESSURE_UNIT_LABELS[new_unit]}")
        self.fc_spin.setValue(mpa_to_pressure(value_mpa, new_unit))
        self.fc_spin.blockSignals(False)

    def _change_slump_unit(self) -> None:
        if self._refreshing:
            return
        old_unit = "in" if self.slump_spin.suffix().strip() == "in" else "mm"
        value_mm = length_to_mm(self.slump_spin.value(), old_unit)
        new_unit = str(self.slump_unit.currentData())
        self.slump_spin.blockSignals(True)
        if new_unit == "in":
            self.slump_spin.setRange(0.0, 12.0)
            self.slump_spin.setDecimals(2)
            self.slump_spin.setSingleStep(0.25)
            self.slump_spin.setSuffix(" in")
        else:
            self.slump_spin.setRange(0.0, 300.0)
            self.slump_spin.setDecimals(1)
            self.slump_spin.setSingleStep(5.0)
            self.slump_spin.setSuffix(" mm")
        self.slump_spin.setValue(mm_to_length(value_mm, new_unit))
        self.slump_spin.blockSignals(False)

    def refresh(self) -> None:
        self._refreshing = True
        try:
            params = self.state.design.parameters
            fc_unit = str(self.fc_unit.currentData())
            self.fc_spin.blockSignals(True)
            self.fc_spin.setValue(mpa_to_pressure(params.fc_mpa, fc_unit))
            self.fc_spin.blockSignals(False)

            slump_unit = str(self.slump_unit.currentData())
            self.slump_spin.blockSignals(True)
            self.slump_spin.setValue(mm_to_length(params.slump_mm, slump_unit))
            self.slump_spin.blockSignals(False)

            index = self.nms_combo.findData(params.nominal_max_size_mm)
            if index >= 0:
                self.nms_combo.setCurrentIndex(index)
        finally:
            self._refreshing = False

    def _calculate_suggestion(self) -> None:
        self.state.design.parameters.fc_mpa = self._fc_mpa()
        self.state.design.parameters.slump_mm = self._slump_mm()
        self.state.design.parameters.nominal_max_size_mm = float(self.nms_combo.currentData())
        self._suggestion = self.state.get_suggestion(self.air_entrained_check.isChecked())
        self.water_value.setText(f"{self._suggestion.water_kg_m3:.1f} kg/m³")
        self.ratio_value.setText(f"{self._suggestion.w_cm:.3f}")
        self.air_value.setText(f"{self._suggestion.air_pct:.1f} %")
        self.note_label.setText(self._suggestion.note)
        self.apply_button.setEnabled(True)

    def _apply_suggestion(self) -> None:
        if self._suggestion is not None:
            self.state.apply_suggestion(self._suggestion)
