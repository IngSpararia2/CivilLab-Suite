from __future__ import annotations

from functools import partial

from PySide6.QtCore import QLocale, Qt, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from civillab_suite.ui.shared_controls import (
    SHARED_CONTROL_ASSETS_DIR,
    ExplicitFocusDoubleSpinBox,
    ensure_table_row_height,
)
from concrete_mix_designer.domain.models import CATEGORY_LABELS, ConstraintMode, MaterialCategory
from concrete_mix_designer.services.app_state import AppState
from concrete_mix_designer.ui.dialogs.inverse_mix_calculator_dialog import (
    InverseMixCalculatorDialog,
)
from concrete_mix_designer.ui.dialogs.ratio_constraint_dialog import (
    CONSTRAINT_LABELS,
    RatioConstraintDialog,
)
from concrete_mix_designer.ui.widgets.volume_stack import VolumeStackWidget

TARGET_SUFFIXES = {
    ConstraintMode.MASS_RATIO: " A/B",
    ConstraintMode.PERCENT_OF_B: " %",
    ConstraintMode.PERCENT_OF_PAIR: " %",
    ConstraintMode.PERCENT_OF_CEMENTITIOUS: " %",
    ConstraintMode.ML_PER_100KG_B: " mL/100 kg",
    ConstraintMode.ML_PER_100KG_CEMENTITIOUS: " mL/100 kg",
}
QUANTITY_ROLE = Qt.ItemDataRole.UserRole + 1

LOCK_COLUMN = 0
MATERIAL_COLUMN = 1
PERCENTAGE_COLUMN = 2
TYPE_COLUMN = 3
QUANTITY_COLUMN = 4
UNIT_COLUMN = 5
SG_COLUMN = 6
VOLUME_COLUMN = 7


class QuantityDelegate(QStyledItemDelegate):
    """Create a numeric editor only while a quantity cell is being edited."""

    quantity_committed = Signal(str, float)

    def __init__(
        self,
        parent=None,
        *,
        maximum: float = 10000.0,
        decimals: int = 3,
        single_step: float = 1.0,
        minimum_width: int = 124,
    ):
        super().__init__(parent)
        self.maximum = maximum
        self.decimals = decimals
        self.single_step = single_step
        self.minimum_width = minimum_width

    def createEditor(self, parent, option, index):  # noqa: N802
        editor = ExplicitFocusDoubleSpinBox(parent)
        editor.setRange(0.0, self.maximum)
        editor.setDecimals(self.decimals)
        editor.setSingleStep(self.single_step)
        editor.setMinimumWidth(self.minimum_width)
        editor.setKeyboardTracking(False)
        editor.editingFinished.connect(lambda: self._finish_editor(editor))
        return editor

    def setEditorData(self, editor, index):  # noqa: N802
        editor.setProperty("_civillab_quantity_committed", False)
        editor.setValue(float(index.data(QUANTITY_ROLE) or 0.0))

    def setModelData(self, editor, model, index):  # noqa: N802
        if editor.property("_civillab_quantity_committed"):
            return
        editor.setProperty("_civillab_quantity_committed", True)
        value = float(editor.value())
        model.setData(index, QLocale().toString(value, "f", self.decimals), Qt.DisplayRole)
        model.setData(index, value, QUANTITY_ROLE)
        uid = index.data(Qt.ItemDataRole.UserRole)
        if uid is not None:
            self.quantity_committed.emit(str(uid), value)

    def _finish_editor(self, editor: ExplicitFocusDoubleSpinBox) -> None:
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)
        editor.deleteLater()


class WorkspacePage(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self._refreshing = False

        title = QLabel("Laboratorio de diseño")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Edita cantidades y candados en la tabla superior. Define proporciones y dosis como reglas visibles en la tabla inferior."
        )
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)
        self.save_design_button = QPushButton("Guardar diseño calculado")
        self.save_design_button.setToolTip(
            "Guardar el diseño actual en la biblioteca"
        )
        subtitle_row = QHBoxLayout()
        subtitle_row.setContentsMargins(0, 0, 0, 0)
        subtitle_row.setSpacing(14)
        subtitle_row.addWidget(subtitle, 1)
        subtitle_row.addWidget(self.save_design_button, 0, Qt.AlignTop)

        self.auto_check = QCheckBox("Recalcular al confirmar cada campo")
        self.auto_check.setChecked(state.auto_recalculate)
        self.auto_check.toggled.connect(state.set_auto_recalculate)
        self.manual_button = QPushButton("Aplicar y cerrar a 1000 L")
        self.manual_button.setObjectName("Secondary")
        self.manual_button.clicked.connect(lambda: state.recalculate())
        self.pending_label = QLabel()
        self.pending_label.setObjectName("StatusPill")
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.auto_check)
        mode_row.addWidget(self.manual_button)
        mode_row.addWidget(self.pending_label)
        mode_row.addStretch()

        self.ratio_spin = ExplicitFocusDoubleSpinBox()
        self.ratio_spin.setRange(0.10, 1.50)
        self.ratio_spin.setDecimals(3)
        self.ratio_spin.setSingleStep(0.005)
        self.ratio_spin.setKeyboardTracking(False)
        self.ratio_spin.editingFinished.connect(self._ratio_finished)
        self.ratio_lock = QCheckBox("Bloquear relación a/mc")
        self.ratio_lock.toggled.connect(self._ratio_lock_changed)
        self.percentage_check = QCheckBox("Calcular por porcentaje")
        percentage_tooltip = (
            "El 100 % corresponde a los componentes expresados en kg. "
            "El aire se mantiene en litros y se descuenta del volumen disponible."
        )
        self.percentage_check.setToolTip(percentage_tooltip)
        self.percentage_check.toggled.connect(self._percentage_mode_changed)
        self.percentage_total_label = QLabel("Σ 100,000 %")
        self.percentage_total_label.setObjectName("StatusPill")
        self.percentage_total_label.setToolTip(percentage_tooltip)
        self.inverse_calculator_button = QToolButton()
        self.inverse_calculator_button.setIcon(
            QIcon(str(SHARED_CONTROL_ASSETS_DIR / "calculator.svg"))
        )
        self.inverse_calculator_button.setToolTip("Calculadora inversa de mezcla")
        self.inverse_calculator_button.setAccessibleName("Calculadora inversa de mezcla")
        self.inverse_calculator_button.clicked.connect(self._open_inverse_calculator)
        ratio_row = QHBoxLayout()
        ratio_row.addWidget(QLabel("Relación agua/material cementante:"))
        ratio_row.addWidget(self.ratio_spin)
        ratio_row.addWidget(self.ratio_lock)
        ratio_row.addWidget(self.percentage_check)
        ratio_row.addWidget(self.percentage_total_label)
        ratio_row.addWidget(self.inverse_calculator_button)
        ratio_row.addStretch()

        # Keep the percentage column permanent so delegates and column indices
        # remain stable when the alternate calculation mode is toggled.
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Candado",
                "Material",
                "Porcentaje %",
                "Tipo",
                "Cantidad",
                "Unidad",
                "G.E.",
                "Volumen L",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.quantity_delegate = QuantityDelegate(self.table)
        self.quantity_delegate.quantity_committed.connect(self._quantity_committed)
        self.percentage_delegate = QuantityDelegate(
            self.table,
            maximum=100.0,
            decimals=3,
            single_step=0.1,
            minimum_width=118,
        )
        self.percentage_delegate.quantity_committed.connect(self._percentage_committed)
        self.table.setItemDelegateForColumn(QUANTITY_COLUMN, self.quantity_delegate)
        self.table.setItemDelegateForColumn(PERCENTAGE_COLUMN, self.percentage_delegate)
        self.table.cellClicked.connect(self._start_quantity_edit)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(MATERIAL_COLUMN, QHeaderView.Stretch)
        header.setSectionResizeMode(TYPE_COLUMN, QHeaderView.ResizeToContents)
        for column in (LOCK_COLUMN, UNIT_COLUMN, SG_COLUMN, VOLUME_COLUMN):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(PERCENTAGE_COLUMN, QHeaderView.Interactive)
        header.resizeSection(PERCENTAGE_COLUMN, 128)
        header.setSectionResizeMode(QUANTITY_COLUMN, QHeaderView.Interactive)
        header.resizeSection(QUANTITY_COLUMN, 136)
        self.table.setColumnHidden(PERCENTAGE_COLUMN, True)

        self.material_combo = QComboBox()
        self.add_component_button = QPushButton("Agregar componente")
        self.add_component_button.clicked.connect(self._add_component)
        self.remove_component_button = QPushButton("Eliminar seleccionado")
        self.remove_component_button.setObjectName("Danger")
        self.remove_component_button.clicked.connect(self._remove_selected)
        component_controls = QHBoxLayout()
        component_controls.addWidget(self.material_combo, 1)
        component_controls.addWidget(self.add_component_button)
        component_controls.addWidget(self.remove_component_button)

        relations_title = QLabel("Relaciones y dosificaciones")
        relations_title.setObjectName("SectionTitle")
        relations_help = QLabel(
            "Crea una regla seleccionando materiales que ya están en la tabla. Después escribe el objetivo directamente en la columna Objetivo."
        )
        relations_help.setWordWrap(True)
        relations_help.setObjectName("Subtitle")

        self.constraints_table = QTableWidget(0, 7)
        self.constraints_table.setHorizontalHeaderLabels(
            ["Activa", "Material A", "Tipo", "Base B", "Objetivo", "Valor actual", "Eliminar"]
        )
        self.constraints_table.verticalHeader().setVisible(False)
        self.constraints_table.verticalHeader().setDefaultSectionSize(36)
        self.constraints_table.setAlternatingRowColors(True)
        constraints_header = self.constraints_table.horizontalHeader()
        constraints_header.setSectionResizeMode(1, QHeaderView.Stretch)
        constraints_header.setSectionResizeMode(2, QHeaderView.Stretch)
        constraints_header.setSectionResizeMode(3, QHeaderView.Stretch)
        for column in (0, 4, 5):
            constraints_header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        constraints_header.setSectionResizeMode(4, QHeaderView.Interactive)
        constraints_header.resizeSection(4, 176)
        constraints_header.setSectionResizeMode(6, QHeaderView.Interactive)
        constraints_header.resizeSection(6, 104)
        constraints_header.setMinimumSectionSize(54)

        self.add_constraint_button = QPushButton("Añadir relación o dosificación")
        self.add_constraint_button.clicked.connect(self._add_constraint)

        left_card = QFrame()
        left_card.setObjectName("Card")
        left_layout = QVBoxLayout(left_card)
        left_layout.addLayout(mode_row)
        left_layout.addLayout(ratio_row)
        left_layout.addWidget(self.table, 2)
        left_layout.addLayout(component_controls)
        left_layout.addSpacing(6)
        left_layout.addWidget(relations_title)
        left_layout.addWidget(relations_help)
        left_layout.addWidget(self.constraints_table, 1)
        left_layout.addWidget(self.add_constraint_button)

        self.volume_widget = VolumeStackWidget()
        self.total_metric = QLabel("—")
        self.total_metric.setObjectName("Metric")
        self.wcm_metric = QLabel("—")
        self.wcm_metric.setObjectName("Metric")
        self.sand_metric = QLabel("—")
        self.sand_metric.setObjectName("Metric")
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setObjectName("WarningBanner")
        right_card = QFrame()
        right_card.setObjectName("Card")
        right_card.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        right_layout = QVBoxLayout(right_card)
        right_layout.addWidget(self.volume_widget, 1)
        right_layout.addLayout(self._metric_row("Volumen total", self.total_metric))
        right_layout.addLayout(self._metric_row("a/mc real", self.wcm_metric))
        right_layout.addLayout(self._metric_row("Arena / agregado", self.sand_metric))
        right_layout.addWidget(self.warning_label)

        content = QSplitter(Qt.Horizontal)
        content.setChildrenCollapsible(False)
        content.addWidget(left_card)
        content.addWidget(right_card)
        content.setStretchFactor(0, 4)
        content.setStretchFactor(1, 1)
        content.setSizes([1048, 272])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.addWidget(title)
        layout.addLayout(subtitle_row)
        layout.addWidget(content, 1)

        state.design_changed.connect(self.refresh)
        state.materials_changed.connect(self._refresh_material_combo)
        state.calculation_mode_changed.connect(self.refresh)
        self.refresh()
        self._refresh_material_combo()

    @staticmethod
    def _metric_row(label: str, widget: QLabel) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addWidget(QLabel(label))
        layout.addStretch()
        layout.addWidget(widget)
        return layout

    def _refresh_material_combo(self) -> None:
        current = self.material_combo.currentData()
        self.material_combo.clear()
        for material in self.state.materials:
            self.material_combo.addItem(
                f"{material.name} · {CATEGORY_LABELS[material.category]}", material.id
            )
        index = self.material_combo.findData(current)
        if index >= 0:
            self.material_combo.setCurrentIndex(index)

    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        try:
            design = self.state.design
            self.auto_check.blockSignals(True)
            self.auto_check.setChecked(self.state.auto_recalculate)
            self.auto_check.blockSignals(False)
            self.manual_button.setEnabled(not self.state.auto_recalculate or self.state.is_dirty)
            self.pending_label.setText("Cambios pendientes" if self.state.is_dirty else "")
            self.pending_label.setVisible(self.state.is_dirty)

            percentage_mode = self.state.percentage_mode
            self.percentage_check.blockSignals(True)
            self.percentage_check.setChecked(percentage_mode)
            self.percentage_check.blockSignals(False)
            self.table.setColumnHidden(PERCENTAGE_COLUMN, not percentage_mode)
            self.percentage_total_label.setVisible(percentage_mode)
            total_percentage = self.state.percentage_total
            self.percentage_total_label.setText(f"Σ {total_percentage:.3f} %")
            percentage_valid = self.state.percentage_design_is_valid
            self.percentage_total_label.setStyleSheet(
                "color: #176b43; font-weight: 700;"
                if percentage_valid
                else "color: #b54708; font-weight: 700;"
            )
            suspended_tooltip = (
                "Este control está temporalmente suspendido mientras se calcula por porcentaje."
            )
            for widget in (
                self.ratio_spin,
                self.ratio_lock,
                self.add_component_button,
                self.remove_component_button,
                self.add_constraint_button,
            ):
                widget.setEnabled(not percentage_mode)
                widget.setToolTip(suspended_tooltip if percentage_mode else "")
            self.manual_button.setEnabled(
                not percentage_mode
                and (not self.state.auto_recalculate or self.state.is_dirty)
            )
            self.save_design_button.setEnabled(not percentage_mode or percentage_valid)

            self.ratio_spin.blockSignals(True)
            self.ratio_spin.setValue(design.parameters.target_w_cm)
            self.ratio_spin.blockSignals(False)
            self.ratio_lock.blockSignals(True)
            self.ratio_lock.setChecked(design.parameters.w_cm_locked)
            self.ratio_lock.blockSignals(False)

            self.table.setRowCount(len(design.components))
            for row, component in enumerate(design.components):
                self._populate_row(row, component)
            self._populate_constraints()

            self.volume_widget.set_design(design)
            self.total_metric.setText(f"{design.total_absolute_volume_l:.2f} L")
            self.wcm_metric.setText(f"{design.actual_w_cm:.3f}")
            self.sand_metric.setText(f"{design.fine_aggregate_pct:.1f} %")
            warnings = "\n".join(design.warnings) if design.warnings else "Sin conflictos de restricciones."
            self.warning_label.setText(warnings)
        finally:
            self._refreshing = False

    def _populate_row(self, row: int, component) -> None:
        percentage_mode = self.state.percentage_mode
        relation_controlled = component.uid in self.state.design.relation_controlled_uids
        lock_button = QToolButton()
        lock_button.setCheckable(True)
        lock_button.setChecked(component.locked)
        lock_button.setText("🔒" if component.locked else "🔓")
        lock_button.setEnabled(not percentage_mode)
        lock_button.setToolTip(
            "Candado temporalmente suspendido durante el cálculo por porcentaje."
            if percentage_mode
            else "Bloquear o liberar este componente"
        )
        lock_button.toggled.connect(partial(self._lock_changed, component.uid, lock_button))
        self.table.setCellWidget(row, LOCK_COLUMN, lock_button)

        name_item = QTableWidgetItem(component.material.name)
        name_item.setData(Qt.UserRole, component.uid)
        self.table.setItem(row, MATERIAL_COLUMN, name_item)

        percentage = QTableWidgetItem()
        percentage.setData(Qt.ItemDataRole.UserRole, component.uid)
        percentage.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if component.category == MaterialCategory.AIR:
            percentage.setText("—")
            percentage.setFlags(percentage.flags() & ~Qt.ItemFlag.ItemIsEditable)
            percentage.setToolTip("El aire se mantiene en litros y no participa en el 100 % por masa.")
        else:
            value = self.state.percentage_values.get(component.uid, 0.0)
            percentage.setText(QLocale().toString(value, "f", 3))
            percentage.setData(QUANTITY_ROLE, value)
            if not percentage_mode:
                percentage.setFlags(percentage.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, PERCENTAGE_COLUMN, percentage)
        self.table.setItem(row, TYPE_COLUMN, QTableWidgetItem(CATEGORY_LABELS[component.category]))

        quantity = QTableWidgetItem(QLocale().toString(component.quantity, "f", 3))
        quantity.setData(Qt.ItemDataRole.UserRole, component.uid)
        quantity.setData(QUANTITY_ROLE, component.quantity)
        quantity.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if percentage_mode:
            quantity.setFlags(quantity.flags() & ~Qt.ItemFlag.ItemIsEditable)
            quantity.setBackground(QColor("#e7eef6"))
            quantity.setForeground(QColor("#60758a"))
            quantity.setToolTip("Cantidad calculada a partir del porcentaje por masa.")
        elif relation_controlled:
            tooltip = (
                "Cantidad controlada automáticamente por una relación o dosificación activa."
            )
            quantity.setToolTip(tooltip)
            quantity.setFlags(quantity.flags() & ~Qt.ItemFlag.ItemIsEditable)
            quantity.setBackground(QColor("#e7eef6"))
            quantity.setForeground(QColor("#60758a"))
            name_item.setToolTip(tooltip)
        self.table.setItem(row, QUANTITY_COLUMN, quantity)
        self.table.setItem(row, UNIT_COLUMN, QTableWidgetItem(component.unit))
        self.table.setItem(
            row, SG_COLUMN, QTableWidgetItem(f"{component.material.specific_gravity:.3f}")
        )
        self.table.setItem(row, VOLUME_COLUMN, QTableWidgetItem(f"{component.absolute_volume_l:.3f}"))
        ensure_table_row_height(self.table, row)

    def _populate_constraints(self) -> None:
        constraints = self.state.design.ratio_constraints
        self.constraints_table.setRowCount(len(constraints))
        for row, constraint in enumerate(constraints):
            numerator = self.state.design.component(constraint.numerator_uid)
            denominator = self.state.design.component(constraint.denominator_uid)

            active = QCheckBox()
            active.setChecked(constraint.enabled)
            active.setEnabled(not self.state.percentage_mode)
            active.setToolTip(
                "Relación suspendida durante el cálculo por porcentaje."
                if self.state.percentage_mode
                else ""
            )
            active.toggled.connect(
                lambda checked, uid=constraint.uid, c=constraint: self.state.update_ratio_constraint(
                    uid, c.target_ratio, checked
                )
            )
            self.constraints_table.setCellWidget(row, 0, active)
            self.constraints_table.setItem(
                row,
                1,
                QTableWidgetItem(numerator.material.name if numerator else "Material eliminado"),
            )
            self.constraints_table.setItem(
                row, 2, QTableWidgetItem(CONSTRAINT_LABELS[constraint.mode])
            )
            base_name = denominator.material.name if denominator else "Cementante total"
            self.constraints_table.setItem(row, 3, QTableWidgetItem(base_name))

            target = ExplicitFocusDoubleSpinBox()
            target.setRange(0.0, 100000.0)
            target.setDecimals(6)
            target.setKeyboardTracking(False)
            target.setValue(constraint.target_ratio)
            target.setSuffix(TARGET_SUFFIXES[constraint.mode])
            target.setEnabled(not self.state.percentage_mode)
            target.editingFinished.connect(
                lambda uid=constraint.uid, a=active, widget=target: self.state.update_ratio_constraint(
                    uid, widget.value(), a.isChecked()
                )
            )
            self.constraints_table.setCellWidget(row, 4, target)

            actual = self.state.engine.constraint_actual_value(self.state.design, constraint)
            actual_item = QTableWidgetItem(
                f"{actual:.6f}{TARGET_SUFFIXES[constraint.mode]}"
            )
            actual_item.setTextAlignment(Qt.AlignCenter)
            self.constraints_table.setItem(row, 5, actual_item)

            delete = QPushButton("Eliminar")
            delete.setEnabled(not self.state.percentage_mode)
            delete.clicked.connect(
                lambda _checked=False, uid=constraint.uid: self.state.remove_ratio_constraint(uid)
            )
            common_height = max(target.sizeHint().height(), delete.sizeHint().height())
            target.setFixedHeight(common_height)
            delete.setFixedHeight(common_height)
            self.constraints_table.setCellWidget(row, 6, delete)
            ensure_table_row_height(self.constraints_table, row, vertical_padding=6)

    def _start_quantity_edit(self, row: int, column: int) -> None:
        if column not in (QUANTITY_COLUMN, PERCENTAGE_COLUMN):
            return
        item = self.table.item(row, column)
        if item is not None and item.flags() & Qt.ItemFlag.ItemIsEditable:
            self.table.editItem(item)

    def _quantity_committed(self, uid: str, value: float) -> None:
        component = self.state.design.component(uid)
        if (
            not self._refreshing
            and component is not None
            and abs(component.quantity - value) > 1e-9
        ):
            self.state.set_quantity(uid, value)

    def _percentage_committed(self, uid: str, value: float) -> None:
        if not self._refreshing and self.state.percentage_mode:
            self.state.set_percentage(uid, value)

    def _percentage_mode_changed(self, checked: bool) -> None:
        if self._refreshing:
            return
        try:
            self.state.set_percentage_mode(checked)
        except ValueError as error:
            self.percentage_check.blockSignals(True)
            self.percentage_check.setChecked(False)
            self.percentage_check.blockSignals(False)
            QMessageBox.warning(self, "No se puede calcular por porcentaje", str(error))

    def _open_inverse_calculator(self) -> None:
        dialog = InverseMixCalculatorDialog(
            self.state.materials,
            [component.material for component in self.state.design.enabled_components()],
            self,
        )
        if dialog.exec():
            try:
                self.state.replace_with_normalized_recipe(dialog.normalized_entries)
                self.state.message.emit("La receta inversa normalizada se añadió al Laboratorio.")
            except ValueError as error:
                QMessageBox.warning(self, "No se pudo aplicar la receta", str(error))

    def _lock_changed(self, uid: str, button: QToolButton, checked: bool) -> None:
        button.setText("🔒" if checked else "🔓")
        if not self._refreshing:
            self.state.set_locked(uid, checked)

    def _ratio_finished(self) -> None:
        if not self._refreshing:
            self.state.update_parameters(target_w_cm=self.ratio_spin.value())

    def _ratio_lock_changed(self, checked: bool) -> None:
        if not self._refreshing:
            self.state.update_parameters(w_cm_locked=checked)

    def _add_component(self) -> None:
        material_id = self.material_combo.currentData()
        material = next((item for item in self.state.materials if item.id == material_id), None)
        if material is not None:
            try:
                self.state.add_component(material)
            except ValueError as error:
                QMessageBox.warning(self, "No se puede agregar", str(error))

    def _remove_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Selecciona un componente", "Selecciona una fila para eliminarla."
            )
            return
        uid = self.table.item(row, 1).data(Qt.UserRole)
        component = self.state.design.component(uid)
        if component and component.category in (MaterialCategory.WATER, MaterialCategory.AIR):
            answer = QMessageBox.question(
                self, "Eliminar componente esencial", f"¿Eliminar {component.material.name}?"
            )
            if answer != QMessageBox.Yes:
                return
        self.state.remove_component(uid)

    def _add_constraint(self) -> None:
        if len(self.state.design.enabled_components()) < 1:
            QMessageBox.information(
                self, "Sin componentes", "Agrega al menos un componente al diseño."
            )
            return
        dialog = RatioConstraintDialog(self.state.design.enabled_components(), self)
        if dialog.exec():
            try:
                self.state.add_ratio_constraint(*dialog.values())
            except ValueError as error:
                QMessageBox.warning(self, "Relación inválida", str(error))
