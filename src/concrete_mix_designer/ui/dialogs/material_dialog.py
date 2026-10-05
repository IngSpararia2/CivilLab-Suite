from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from concrete_mix_designer.domain.metadata_models import MaterialCharacterization
from concrete_mix_designer.domain.models import (
    CATEGORY_LABELS,
    DosageMode,
    Material,
    MaterialCategory,
)
from concrete_mix_designer.ui.dialogs.granulometry_dialog import GranulometryDialog


def _optional_spin(
    maximum: float,
    decimals: int = 3,
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


class MaterialDialog(QDialog):
    def __init__(
        self,
        material: Material | None = None,
        characterization: MaterialCharacterization | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.material = material
        self._gradation = list((characterization or MaterialCharacterization()).gradation)
        self.setWindowTitle("Editar material" if material else "Nuevo material")
        self.resize(720, 780)

        self.name_edit = QLineEdit()
        self.code_edit = QLineEdit(material.code if material else "")
        self.code_edit.setPlaceholderText("Código compartido; vacío para generar uno")
        self.code_edit.setReadOnly(material is not None)
        self.code_edit.setToolTip("Un código existente de la misma categoría referencia la identidad de Core.")
        self.category_combo = QComboBox()
        for category, label in CATEGORY_LABELS.items():
            self.category_combo.addItem(label, category)
        self.category_combo.currentIndexChanged.connect(self._update_category_sections)

        self.sg_spin = QDoubleSpinBox()
        self.sg_spin.setRange(0.01, 10.0)
        self.sg_spin.setDecimals(4)
        self.sg_spin.setValue(2.65)
        self.sg_spin.setKeyboardTracking(False)
        self.absorption_spin = QDoubleSpinBox()
        self.absorption_spin.setRange(0.0, 100.0)
        self.absorption_spin.setDecimals(3)
        self.absorption_spin.setSuffix(" %")
        self.moisture_spin = QDoubleSpinBox()
        self.moisture_spin.setRange(0.0, 100.0)
        self.moisture_spin.setDecimals(3)
        self.moisture_spin.setSuffix(" %")

        basic_group = QGroupBox("Identificación y propiedades usadas en el cálculo")
        basic_form = QFormLayout(basic_group)
        basic_form.addRow("Código canónico:", self.code_edit)
        basic_form.addRow("Nombre:*", self.name_edit)
        basic_form.addRow("Categoría:*", self.category_combo)
        basic_form.addRow("G.E. cálculo (SSD en agregados):*", self.sg_spin)
        basic_form.addRow("Absorción:", self.absorption_spin)
        basic_form.addRow("Humedad legacy (solo referencia):", self.moisture_spin)
        self.moisture_spin.setReadOnly(True)
        self.moisture_spin.setToolTip("Introduce la humedad actual en Dosificación o al registrar cada producción.")

        self.supplier_edit = QLineEdit()
        self.source_edit = QLineEdit()
        self.lot_edit = QLineEdit()
        self.standard_edit = QLineEdit()
        general_group = QGroupBox("Trazabilidad de la caracterización")
        general_form = QFormLayout(general_group)
        general_form.addRow("Proveedor:", self.supplier_edit)
        general_form.addRow("Fuente / cantera / planta:", self.source_edit)
        general_form.addRow("Lote o identificación:", self.lot_edit)
        general_form.addRow("Norma o procedimiento:", self.standard_edit)

        self.sg_dry = _optional_spin(10.0, 4)
        self.sg_ssd = _optional_spin(10.0, 4)
        self.sg_ssd.setToolTip("Base SSD usada para el cálculo; actualiza la G.E. de cálculo.")
        self.sg_ssd.valueChanged.connect(lambda value: self.sg_spin.setValue(value) if value>0 and self.category in (MaterialCategory.FINE_AGGREGATE,MaterialCategory.COARSE_AGGREGATE) else None)
        self.sg_spin.valueChanged.connect(lambda value: self.sg_ssd.setValue(value) if self.category in (MaterialCategory.FINE_AGGREGATE,MaterialCategory.COARSE_AGGREGATE) else None)
        self.compacted_unit_weight = _optional_spin(5000.0, 1, " kg/m³")
        self.fineness_modulus = _optional_spin(10.0, 2)
        self.nominal_max_size = _optional_spin(200.0, 2, " mm")
        self.aggregate_shape = QComboBox()
        self.aggregate_shape.addItems(
            ["", "Triturado/angular", "Subangular", "Subredondeado", "Redondeado"]
        )
        self.aggregate_texture = QComboBox()
        self.aggregate_texture.addItems(["", "Lisa", "Intermedia", "Rugosa", "Porosa"])
        self.gradation_summary = QLabel("Sin granulometría registrada")
        self.gradation_summary.setWordWrap(True)
        self.gradation_summary.setObjectName("Subtitle")
        gradation_button = QPushButton("Añadir o editar granulometría…")
        gradation_button.clicked.connect(self._edit_gradation)
        gradation_row = QWidget()
        gradation_layout = QHBoxLayout(gradation_row)
        gradation_layout.setContentsMargins(0, 0, 0, 0)
        gradation_layout.addWidget(gradation_button)
        gradation_layout.addWidget(self.gradation_summary, 1)

        self.aggregate_group = QGroupBox("Caracterización de agregados")
        aggregate_form = QFormLayout(self.aggregate_group)
        aggregate_form.addRow("Gravedad específica seca:", self.sg_dry)
        aggregate_form.addRow("Gravedad específica SSS:", self.sg_ssd)
        aggregate_form.addRow("Masa unitaria compactada:", self.compacted_unit_weight)
        aggregate_form.addRow("Módulo de finura:", self.fineness_modulus)
        aggregate_form.addRow("Tamaño máximo nominal:", self.nominal_max_size)
        aggregate_form.addRow("Forma:", self.aggregate_shape)
        aggregate_form.addRow("Textura:", self.aggregate_texture)
        aggregate_form.addRow("Granulometría:", gradation_row)

        self.cement_type = QLineEdit()
        self.cement_type.setPlaceholderText("Ej. Tipo I, Tipo III, cemento adicionado")
        self.cement_group = QGroupBox("Caracterización del cementante")
        cement_form = QFormLayout(self.cement_group)
        cement_form.addRow("Tipo / clase del cementante:", self.cement_type)

        self.admixture_density = _optional_spin(10.0, 4, " kg/L")
        self.water_reduction = _optional_spin(100.0, 2, " %")
        self.recommended_dosage = _optional_spin(100.0, 3, " % cementante")
        self.admixture_group = QGroupBox("Caracterización del aditivo")
        admixture_form = QFormLayout(self.admixture_group)
        admixture_form.addRow("Densidad:", self.admixture_density)
        admixture_form.addRow("Reducción de agua declarada:", self.water_reduction)
        admixture_form.addRow("Dosificación recomendada:", self.recommended_dosage)

        self.notes = QPlainTextEdit()
        self.notes.setMaximumHeight(100)
        self.notes.setPlaceholderText(
            "Resultados complementarios, observaciones de forma, almacenamiento o restricciones de uso."
        )
        notes_group = QGroupBox("Observaciones")
        notes_layout = QVBoxLayout(notes_group)
        notes_layout.addWidget(self.notes)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.addWidget(basic_group)
        content_layout.addWidget(general_group)
        content_layout.addWidget(self.aggregate_group)
        content_layout.addWidget(self.cement_group)
        content_layout.addWidget(self.admixture_group)
        content_layout.addWidget(notes_group)
        content_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addWidget(buttons)

        if material:
            self._load_material(material)
        if characterization:
            self._load_characterization(characterization)
        self._update_category_sections()
        self._refresh_gradation_summary()

    @property
    def category(self) -> MaterialCategory:
        return MaterialCategory(self.category_combo.currentData())

    def _load_material(self, material: Material) -> None:
        self.name_edit.setText(material.name)
        index = self.category_combo.findData(material.category)
        if index >= 0:
            self.category_combo.setCurrentIndex(index)
        self.sg_spin.setValue(material.specific_gravity)
        self.absorption_spin.setValue(material.absorption_pct)
        self.moisture_spin.setValue(material.moisture_pct)

    def _set_optional(self, widget: QDoubleSpinBox, value: float | None) -> None:
        widget.setValue(-1.0 if value is None else float(value))

    def _load_characterization(self, value: MaterialCharacterization) -> None:
        self.supplier_edit.setText(value.supplier)
        self.source_edit.setText(value.source)
        self.lot_edit.setText(value.lot_code)
        self.standard_edit.setText(value.characterization_standard)
        self.cement_type.setText(value.cement_type)
        self._set_optional(self.sg_dry, value.specific_gravity_dry)
        self._set_optional(self.sg_ssd, value.specific_gravity_ssd)
        self._set_optional(self.compacted_unit_weight, value.compacted_unit_weight_kg_m3)
        self._set_optional(self.fineness_modulus, value.fineness_modulus)
        self._set_optional(self.nominal_max_size, value.nominal_max_size_mm)
        self.aggregate_shape.setCurrentText(value.aggregate_shape)
        self.aggregate_texture.setCurrentText(value.aggregate_texture)
        self._set_optional(self.admixture_density, value.admixture_density_kg_l)
        self._set_optional(self.water_reduction, value.water_reduction_pct)
        self._set_optional(self.recommended_dosage, value.recommended_dosage_pct)
        self.notes.setPlainText(value.notes)
        self._gradation = list(value.gradation)

    def _update_category_sections(self) -> None:
        category = self.category
        is_aggregate = category in {
            MaterialCategory.FINE_AGGREGATE,
            MaterialCategory.COARSE_AGGREGATE,
        }
        self.aggregate_group.setVisible(is_aggregate)
        self.cement_group.setVisible(category == MaterialCategory.CEMENTITIOUS)
        self.admixture_group.setVisible(category == MaterialCategory.ADMIXTURE)
        self.fineness_modulus.setEnabled(category == MaterialCategory.FINE_AGGREGATE)
        self.compacted_unit_weight.setEnabled(category == MaterialCategory.COARSE_AGGREGATE)
        self.nominal_max_size.setEnabled(category == MaterialCategory.COARSE_AGGREGATE)

    def _edit_gradation(self) -> None:
        if self.category not in {
            MaterialCategory.FINE_AGGREGATE,
            MaterialCategory.COARSE_AGGREGATE,
        }:
            return
        dialog = GranulometryDialog(self.category, self._gradation, self)
        if dialog.exec():
            self._gradation = dialog.gradation
            if (
                self.category == MaterialCategory.FINE_AGGREGATE
                and dialog.fineness_modulus is not None
            ):
                self.fineness_modulus.setValue(dialog.fineness_modulus)
            self._refresh_gradation_summary()

    def _refresh_gradation_summary(self) -> None:
        completed = sum(point.passing_pct is not None for point in self._gradation)
        self.gradation_summary.setText(
            f"{completed} tamices con dato"
            if completed
            else "Sin granulometría registrada"
        )

    def _validate_and_accept(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Dato requerido", "Escribe el nombre del material.")
            return
        if self.category in {
            MaterialCategory.FINE_AGGREGATE,
            MaterialCategory.COARSE_AGGREGATE,
        }:
            dry = _optional_value(self.sg_dry)
            ssd = _optional_value(self.sg_ssd)
            if dry is not None and ssd is not None and ssd < dry:
                QMessageBox.warning(
                    self,
                    "Datos inconsistentes",
                    "La gravedad específica SSS no debería ser menor que la gravedad específica seca.",
                )
                return
        self.accept()

    def result_material(self) -> Material:
        return Material(
            id=self.material.id if self.material else None,
            name=self.name_edit.text().strip(),
            category=self.category,
            specific_gravity=self.sg_spin.value(),
            absorption_pct=self.absorption_spin.value(),
            moisture_pct=self.moisture_spin.value(),
            dosage_mode=(
                self.material.dosage_mode if self.material else DosageMode.MANUAL_KG
            ),
            dosage_value=self.material.dosage_value if self.material else 0.0,
            is_seed=self.material.is_seed if self.material else False,
            canonical_id=self.material.canonical_id if self.material else None,
            code=self.code_edit.text().strip(),
        )

    @property
    def characterization(self) -> MaterialCharacterization:
        is_aggregate = self.category in {
            MaterialCategory.FINE_AGGREGATE,
            MaterialCategory.COARSE_AGGREGATE,
        }
        is_fine = self.category == MaterialCategory.FINE_AGGREGATE
        is_coarse = self.category == MaterialCategory.COARSE_AGGREGATE
        is_cementitious = self.category == MaterialCategory.CEMENTITIOUS
        is_admixture = self.category == MaterialCategory.ADMIXTURE
        return MaterialCharacterization(
            material_id=self.material.id if self.material else None,
            supplier=self.supplier_edit.text().strip(),
            source=self.source_edit.text().strip(),
            lot_code=self.lot_edit.text().strip(),
            characterization_standard=self.standard_edit.text().strip(),
            cement_type=self.cement_type.text().strip() if is_cementitious else "",
            specific_gravity_dry=_optional_value(self.sg_dry) if is_aggregate else None,
            specific_gravity_ssd=_optional_value(self.sg_ssd) if is_aggregate else None,
            compacted_unit_weight_kg_m3=(
                _optional_value(self.compacted_unit_weight) if is_coarse else None
            ),
            fineness_modulus=_optional_value(self.fineness_modulus) if is_fine else None,
            nominal_max_size_mm=_optional_value(self.nominal_max_size) if is_coarse else None,
            aggregate_shape=self.aggregate_shape.currentText().strip() if is_aggregate else "",
            aggregate_texture=self.aggregate_texture.currentText().strip() if is_aggregate else "",
            admixture_density_kg_l=(
                _optional_value(self.admixture_density) if is_admixture else None
            ),
            water_reduction_pct=(
                _optional_value(self.water_reduction) if is_admixture else None
            ),
            recommended_dosage_pct=(
                _optional_value(self.recommended_dosage) if is_admixture else None
            ),
            notes=self.notes.toPlainText().strip(),
            gradation=list(self._gradation) if is_aggregate else [],
        )
