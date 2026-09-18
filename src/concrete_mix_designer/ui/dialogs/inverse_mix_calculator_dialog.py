from __future__ import annotations

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from civillab_suite.ui.shared_controls import ExplicitFocusDoubleSpinBox, ensure_table_row_height
from concrete_mix_designer.domain.mix_normalization import (
    NormalizedRecipe,
    RecipeEntry,
    normalize_observed_recipe,
)
from concrete_mix_designer.domain.models import CATEGORY_LABELS, Material, MaterialCategory


class InverseMixCalculatorDialog(QDialog):
    """Normalize an observed recipe to 1 m³ using absolute volumes."""

    MATERIAL_COLUMN = 0
    TYPE_COLUMN = 1
    SG_COLUMN = 2
    OBSERVED_COLUMN = 3
    UNIT_COLUMN = 4
    VOLUME_COLUMN = 5
    NORMALIZED_COLUMN = 6

    def __init__(self, materials: list[Material], current_materials: list[Material], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calculadora inversa de mezcla")
        self.resize(1050, 540)
        self.materials = list(materials)
        self.normalized_entries: list[tuple[Material, float]] = []
        self._result: NormalizedRecipe | None = None
        self._refreshing = False

        intro = QLabel(
            "Ingresa las cantidades de la receta observada. Los materiales en kg usan "
            "volumen absoluto (kg/G.E.); el aire se ingresa directamente en litros."
        )
        intro.setWordWrap(True)
        intro.setObjectName("Subtitle")

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "Material",
                "Tipo",
                "G.E.",
                "Cantidad observada",
                "Unidad",
                "Volumen abs. (L)",
                "Cantidad para 1 m³",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(self.MATERIAL_COLUMN, header.ResizeMode.Stretch)
        for column in range(1, 7):
            header.setSectionResizeMode(column, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.OBSERVED_COLUMN, header.ResizeMode.Interactive)
        header.resizeSection(self.OBSERVED_COLUMN, 165)

        add_button = QPushButton("Añadir fila")
        add_button.clicked.connect(self._add_empty_row)
        remove_button = QPushButton("Eliminar fila")
        remove_button.setObjectName("Danger")
        remove_button.clicked.connect(self._remove_selected_row)
        row_buttons = QHBoxLayout()
        row_buttons.addWidget(add_button)
        row_buttons.addWidget(remove_button)
        row_buttons.addStretch()

        self.observed_label = QLabel("Volumen estimado: —")
        self.equivalent_label = QLabel("Equivalente: —")
        self.factor_label = QLabel("Factor de escalado: —")
        self.normalized_label = QLabel("Volumen normalizado: —")
        self.wcm_label = QLabel("Relación a/mc: —")
        self.validation_label = QLabel()
        self.validation_label.setObjectName("WarningBanner")
        self.validation_label.setWordWrap(True)

        self.apply_button = QPushButton("Añadir al laboratorio")
        self.apply_button.clicked.connect(self._confirm_apply)
        cancel_button = QPushButton("Cancelar")
        cancel_button.setObjectName("Secondary")
        cancel_button.clicked.connect(self.reject)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.apply_button)
        actions.addWidget(cancel_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.table, 1)
        layout.addLayout(row_buttons)
        for label in (
            self.observed_label,
            self.equivalent_label,
            self.factor_label,
            self.normalized_label,
            self.wcm_label,
        ):
            layout.addWidget(label)
        layout.addWidget(self.validation_label)
        layout.addLayout(actions)

        initial = current_materials or self.materials[:1]
        seen: set[int | None] = set()
        for material in initial:
            if material.id in seen:
                continue
            seen.add(material.id)
            self._append_row(material)
        self._recalculate()

    def _material_key(self, material: Material) -> str:
        return str(material.id) if material.id is not None else f"{material.category}:{material.name}"

    def _material_for_id(self, material_id: int | None) -> Material | None:
        return next((material for material in self.materials if material.id == material_id), None)

    def _append_row(self, selected: Material) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        combo = QComboBox()
        for material in self.materials:
            combo.addItem(material.name, material.id)
        combo.setCurrentIndex(combo.findData(selected.id))
        combo.currentIndexChanged.connect(self._recalculate)
        self.table.setCellWidget(row, self.MATERIAL_COLUMN, combo)

        amount = ExplicitFocusDoubleSpinBox()
        amount.setRange(0.0, 1_000_000.0)
        amount.setDecimals(3)
        amount.setSingleStep(1.0)
        amount.setKeyboardTracking(False)
        amount.setMinimumWidth(145)
        amount.editingFinished.connect(self._recalculate)
        self.table.setCellWidget(row, self.OBSERVED_COLUMN, amount)
        for column in (
            self.TYPE_COLUMN,
            self.SG_COLUMN,
            self.UNIT_COLUMN,
            self.VOLUME_COLUMN,
            self.NORMALIZED_COLUMN,
        ):
            item = QTableWidgetItem("")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, column, item)
        ensure_table_row_height(self.table, row, vertical_padding=6)

    def _add_empty_row(self) -> None:
        selected_ids = {
            self.table.cellWidget(row, self.MATERIAL_COLUMN).currentData()
            for row in range(self.table.rowCount())
        }
        material = next((item for item in self.materials if item.id not in selected_ids), None)
        if material is None:
            QMessageBox.information(
                self, "Sin materiales disponibles", "Todos los materiales registrados ya están en la tabla."
            )
            return
        self._append_row(material)
        self._recalculate()

    def _remove_selected_row(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Selecciona una fila", "Selecciona la fila que deseas eliminar.")
            return
        self.table.removeRow(row)
        self._recalculate()

    def _rows(self) -> list[tuple[Material, float]]:
        rows: list[tuple[Material, float]] = []
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, self.MATERIAL_COLUMN)
            amount = self.table.cellWidget(row, self.OBSERVED_COLUMN)
            material = self._material_for_id(combo.currentData())
            if material is not None:
                rows.append((material, float(amount.value())))
        return rows

    def _recalculate(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        try:
            rows = self._rows()
            entries = [
                RecipeEntry(
                    key=self._material_key(material),
                    quantity=quantity,
                    specific_gravity=material.specific_gravity,
                    is_air=material.category == MaterialCategory.AIR,
                )
                for material, quantity in rows
            ]
            try:
                result = normalize_observed_recipe(entries, 1000.0)
                error_text = ""
            except ValueError as error:
                result = None
                error_text = str(error)
            self._result = result

            for row, (material, _quantity) in enumerate(rows):
                key = self._material_key(material)
                self.table.item(row, self.TYPE_COLUMN).setText(CATEGORY_LABELS[material.category])
                self.table.item(row, self.SG_COLUMN).setText(f"{material.specific_gravity:.3f}")
                self.table.item(row, self.UNIT_COLUMN).setText(
                    "L" if material.category == MaterialCategory.AIR else "kg"
                )
                volume = result.observed_volumes_l[key] if result is not None else None
                normalized = result.quantities[key] if result is not None else None
                self.table.item(row, self.VOLUME_COLUMN).setText(
                    "—" if volume is None else QLocale().toString(volume, "f", 3)
                )
                self.table.item(row, self.NORMALIZED_COLUMN).setText(
                    "—" if normalized is None else QLocale().toString(normalized, "f", 3)
                )

            if result is None:
                self.observed_label.setText("Volumen estimado de la receta observada: —")
                self.equivalent_label.setText("Equivalente: —")
                self.factor_label.setText("Factor de escalado: —")
                self.normalized_label.setText("Volumen normalizado: —")
                self.wcm_label.setText("Relación a/mc resultante: —")
            else:
                self.observed_label.setText(
                    f"Volumen estimado de la receta observada: {result.observed_volume_l:.3f} L"
                )
                self.equivalent_label.setText(
                    f"Equivalente: {result.observed_volume_l / 1000.0:.4f} m³"
                )
                self.factor_label.setText(f"Factor de escalado: {result.scale_factor:.4f}")
                self.normalized_label.setText(
                    f"Volumen normalizado: {result.normalized_volume_l:.3f} L"
                )
                water = sum(
                    result.quantities[self._material_key(material)]
                    for material, _ in rows
                    if material.category == MaterialCategory.WATER
                )
                cement = sum(
                    result.quantities[self._material_key(material)]
                    for material, _ in rows
                    if material.category == MaterialCategory.CEMENTITIOUS
                )
                self.wcm_label.setText(
                    "Relación a/mc resultante: —"
                    if cement <= 0
                    else f"Relación a/mc resultante: {water / cement:.4f}"
                )
            self.validation_label.setText(error_text)
            self.validation_label.setVisible(bool(error_text))
            self.apply_button.setEnabled(result is not None)
        finally:
            self._refreshing = False

    def _confirm_apply(self) -> None:
        if self._result is None:
            return
        answer = QMessageBox.question(
            self,
            "Reemplazar composición actual",
            "La receta normalizada reemplazará todos los componentes y relaciones de la mezcla activa. ¿Continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.normalized_entries = [
            (material, self._result.quantities[self._material_key(material)])
            for material, _quantity in self._rows()
        ]
        self.accept()
