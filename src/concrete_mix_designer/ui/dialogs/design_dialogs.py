from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from concrete_mix_designer.domain.metadata_models import (
    APPLICATION_LABELS,
    CONSISTENCY_LABELS,
    STRENGTH_BASIS_LABELS,
    ConcreteApplication,
    ConsistencyType,
    DesignSpecification,
    StrengthBasis,
)
from concrete_mix_designer.services.unit_conversion import length_to_mm, mm_to_length


def _optional_spin(
    maximum: float,
    decimals: int = 2,
    suffix: str = "",
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(-1.0, maximum)
    spin.setDecimals(decimals)
    spin.setSpecialValueText("—")
    spin.setValue(-1.0)
    spin.setSuffix(suffix)
    spin.setKeyboardTracking(False)
    return spin


def _optional_value(spin: QDoubleSpinBox) -> float | None:
    return None if spin.value() < 0 else float(spin.value())


class SaveDesignDialog(QDialog):
    """Save an independent design and its searchable technical specification."""

    def __init__(
        self,
        *,
        suggested_name: str = "",
        suggested_group: str = "",
        existing_groups: list[str] | None = None,
        suggested_specification: DesignSpecification | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Guardar diseño en la biblioteca")
        self.resize(700, 790)
        specification = suggested_specification or DesignSpecification()

        self.name_edit = QLineEdit(suggested_name)
        self.name_edit.setPlaceholderText("Ej. Pavimento MR 4,2 MPa · TMN 19 mm")

        self.group_combo = QComboBox()
        self.group_combo.setEditable(True)
        self.group_combo.addItem("Sin grupo", "")
        for group in sorted({item.strip() for item in existing_groups or [] if item.strip()}):
            self.group_combo.addItem(group, group)
        if suggested_group:
            index = self.group_combo.findText(suggested_group)
            if index >= 0:
                self.group_combo.setCurrentIndex(index)
            else:
                self.group_combo.setEditText(suggested_group)

        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText(
            "Aplicación prevista, procedencia de materiales, ajustes realizados u observaciones."
        )
        self.description_edit.setMaximumHeight(100)

        identity_group = QGroupBox("Identificación")
        identity_form = QFormLayout(identity_group)
        identity_form.addRow("Nombre:*", self.name_edit)
        identity_form.addRow("Grupo:", self.group_combo)
        identity_form.addRow("Descripción:", self.description_edit)

        self.application_combo = QComboBox()
        for value, label in APPLICATION_LABELS.items():
            self.application_combo.addItem(label, value)
        self.application_combo.setCurrentIndex(
            max(self.application_combo.findData(specification.application_type), 0)
        )

        self.strength_basis_combo = QComboBox()
        for value, label in STRENGTH_BASIS_LABELS.items():
            self.strength_basis_combo.addItem(label, value)
        self.strength_basis_combo.setCurrentIndex(
            max(self.strength_basis_combo.findData(specification.strength_basis), 0)
        )
        self.strength_basis_combo.currentIndexChanged.connect(self._update_visibility)

        self.fc_spin = _optional_spin(150.0, 2, " MPa")
        self.fc_age = QDoubleSpinBox()
        self.fc_age.setRange(0.1, 3650.0)
        self.fc_age.setDecimals(1)
        self.fc_age.setSuffix(" días")
        self.fc_age.setValue(specification.compressive_strength_age_days)
        self.mr_spin = _optional_spin(30.0, 2, " MPa")
        self.mr_age = QDoubleSpinBox()
        self.mr_age.setRange(0.1, 3650.0)
        self.mr_age.setDecimals(1)
        self.mr_age.setSuffix(" días")
        self.mr_age.setValue(specification.modulus_rupture_age_days)
        if specification.expected_compressive_strength_mpa is not None:
            self.fc_spin.setValue(specification.expected_compressive_strength_mpa)
        if specification.expected_modulus_rupture_mpa is not None:
            self.mr_spin.setValue(specification.expected_modulus_rupture_mpa)

        strength_group = QGroupBox("Resistencia esperada")
        strength_form = QFormLayout(strength_group)
        strength_form.addRow("Criterio principal:", self.strength_basis_combo)
        self.fc_label = QLabel("f'c esperada:")
        strength_form.addRow(self.fc_label, self._paired(self.fc_spin, self.fc_age))
        self.mr_label = QLabel("Módulo de rotura esperado:")
        strength_form.addRow(self.mr_label, self._paired(self.mr_spin, self.mr_age))

        self.consistency_combo = QComboBox()
        for value, label in CONSISTENCY_LABELS.items():
            self.consistency_combo.addItem(label, value)
        self.consistency_combo.setCurrentIndex(
            max(self.consistency_combo.findData(specification.consistency_type), 0)
        )
        self.consistency_combo.currentIndexChanged.connect(self._update_visibility)

        self.consistency_value = _optional_spin(1200.0, 1, " mm")
        initial_consistency = specification.consistency_value_mm
        if initial_consistency is not None:
            self.consistency_value.setValue(initial_consistency)
        self.consistency_unit = QComboBox()
        self.consistency_unit.addItem("Milímetros", "mm")
        self.consistency_unit.addItem("Pulgadas", "in")
        self.consistency_unit.currentIndexChanged.connect(self._change_consistency_unit)

        self.initial_set = QSpinBox()
        self.initial_set.setRange(0, 1440)
        self.initial_set.setSpecialValueText("—")
        self.initial_set.setSuffix(" min")
        self.initial_set.setValue(specification.initial_set_minutes or 0)

        self.accelerated_check = QCheckBox("Concreto acelerado")
        self.accelerated_check.setChecked(specification.accelerated)
        self.accelerated_check.toggled.connect(self._update_visibility)
        self.accelerated_age = _optional_spin(3650.0, 1, " días")
        if specification.accelerated_age_days is not None:
            self.accelerated_age.setValue(specification.accelerated_age_days)

        self.nms_spin = _optional_spin(200.0, 1, " mm")
        if specification.nominal_max_size_mm is not None:
            self.nms_spin.setValue(specification.nominal_max_size_mm)
        self.exposure_edit = QLineEdit(specification.exposure_condition)
        self.exposure_edit.setPlaceholderText(
            "Ej. interior seco, sulfatos, ambiente marino, congelamiento y deshielo"
        )
        self.air_entrained = QCheckBox("Requiere aire incluido")
        self.air_entrained.setChecked(specification.air_entrained)
        self.placement_edit = QLineEdit(specification.placement_method)
        self.placement_edit.setPlaceholderText(
            "Ej. bombeado, vaciado directo, pavimentadora, prefabricado"
        )
        self.keywords_edit = QLineEdit(specification.keywords)
        self.keywords_edit.setPlaceholderText(
            "Palabras clave separadas por coma para búsqueda"
        )

        classification_group = QGroupBox("Consistencia y clasificación")
        classification_form = QFormLayout(classification_group)
        classification_form.addRow("Tipo de concreto:", self.application_combo)
        classification_form.addRow("Consistencia:", self.consistency_combo)
        self.consistency_label = QLabel("Valor objetivo:")
        classification_form.addRow(
            self.consistency_label,
            self._paired(self.consistency_value, self.consistency_unit),
        )
        classification_form.addRow("Fraguado inicial previsto:", self.initial_set)
        classification_form.addRow("Aceleración:", self.accelerated_check)
        self.accelerated_age_label = QLabel("Edad objetivo acelerada:")
        classification_form.addRow(self.accelerated_age_label, self.accelerated_age)
        classification_form.addRow("Tamaño máximo nominal:", self.nms_spin)
        classification_form.addRow("Condición de exposición:", self.exposure_edit)
        classification_form.addRow("Aire incluido:", self.air_entrained)
        classification_form.addRow("Método de colocación:", self.placement_edit)
        classification_form.addRow("Etiquetas:", self.keywords_edit)

        help_label = QLabel(
            "Estos datos no cambian las cantidades calculadas: describen y clasifican el diseño "
            "guardado para búsquedas, producción, trazabilidad e informes."
        )
        help_label.setWordWrap(True)
        help_label.setObjectName("Subtitle")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.addWidget(help_label)
        content_layout.addWidget(identity_group)
        content_layout.addWidget(strength_group)
        content_layout.addWidget(classification_group)
        content_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addWidget(buttons)
        self._update_visibility()

    @staticmethod
    def _paired(left: QWidget, right: QWidget) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(left, 1)
        layout.addWidget(right)
        return widget

    def _update_visibility(self) -> None:
        basis = StrengthBasis(self.strength_basis_combo.currentData())
        compression = basis in {StrengthBasis.COMPRESSION, StrengthBasis.BOTH}
        flexural = basis in {StrengthBasis.FLEXURAL, StrengthBasis.BOTH}
        self.fc_label.setVisible(compression)
        self.fc_spin.parentWidget().setVisible(compression)
        self.mr_label.setVisible(flexural)
        self.mr_spin.parentWidget().setVisible(flexural)
        accelerated = self.accelerated_check.isChecked()
        self.accelerated_age_label.setVisible(accelerated)
        self.accelerated_age.setVisible(accelerated)
        consistency = ConsistencyType(self.consistency_combo.currentData())
        self.consistency_label.setText(
            "Esparcimiento objetivo:"
            if consistency == ConsistencyType.SPREAD
            else "Asentamiento objetivo:"
        )

    def _change_consistency_unit(self) -> None:
        value = _optional_value(self.consistency_value)
        old_unit = "in" if self.consistency_value.suffix().strip() == "in" else "mm"
        value_mm = length_to_mm(value, old_unit) if value is not None else None
        new_unit = str(self.consistency_unit.currentData())
        self.consistency_value.blockSignals(True)
        if new_unit == "in":
            self.consistency_value.setRange(-1.0, 50.0)
            self.consistency_value.setDecimals(2)
            self.consistency_value.setSuffix(" in")
        else:
            self.consistency_value.setRange(-1.0, 1200.0)
            self.consistency_value.setDecimals(1)
            self.consistency_value.setSuffix(" mm")
        self.consistency_value.setValue(
            -1.0 if value_mm is None else mm_to_length(value_mm, new_unit)
        )
        self.consistency_value.blockSignals(False)

    def accept(self) -> None:
        if not self.name_edit.text().strip():
            self.name_edit.setFocus()
            return
        basis = StrengthBasis(self.strength_basis_combo.currentData())
        if basis in {StrengthBasis.COMPRESSION, StrengthBasis.BOTH} and _optional_value(self.fc_spin) is None:
            self.fc_spin.setFocus()
            return
        if basis in {StrengthBasis.FLEXURAL, StrengthBasis.BOTH} and _optional_value(self.mr_spin) is None:
            self.mr_spin.setFocus()
            return
        super().accept()

    @property
    def design_name(self) -> str:
        return self.name_edit.text().strip()

    @property
    def group_name(self) -> str:
        data = self.group_combo.currentData()
        if data and self.group_combo.currentText() == self.group_combo.itemText(self.group_combo.currentIndex()):
            return str(data).strip()
        value = self.group_combo.currentText().strip()
        return "" if value == "Sin grupo" else value

    @property
    def description(self) -> str:
        return self.description_edit.toPlainText().strip()

    @property
    def specification(self) -> DesignSpecification:
        consistency = ConsistencyType(self.consistency_combo.currentData())
        value = _optional_value(self.consistency_value)
        value_mm = (
            length_to_mm(value, str(self.consistency_unit.currentData()))
            if value is not None
            else None
        )
        return DesignSpecification(
            application_type=ConcreteApplication(self.application_combo.currentData()),
            strength_basis=StrengthBasis(self.strength_basis_combo.currentData()),
            expected_compressive_strength_mpa=_optional_value(self.fc_spin),
            compressive_strength_age_days=self.fc_age.value(),
            expected_modulus_rupture_mpa=_optional_value(self.mr_spin),
            modulus_rupture_age_days=self.mr_age.value(),
            consistency_type=consistency,
            target_slump_mm=value_mm if consistency == ConsistencyType.SLUMP else None,
            target_spread_mm=value_mm if consistency == ConsistencyType.SPREAD else None,
            initial_set_minutes=(self.initial_set.value() or None),
            accelerated=self.accelerated_check.isChecked(),
            accelerated_age_days=(
                _optional_value(self.accelerated_age)
                if self.accelerated_check.isChecked()
                else None
            ),
            nominal_max_size_mm=_optional_value(self.nms_spin),
            exposure_condition=self.exposure_edit.text().strip(),
            air_entrained=self.air_entrained.isChecked(),
            placement_method=self.placement_edit.text().strip(),
            keywords=self.keywords_edit.text().strip(),
        )
