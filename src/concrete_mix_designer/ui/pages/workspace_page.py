from __future__ import annotations

from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from civillab_suite.ui.shared_controls import (
    ExplicitFocusDoubleSpinBox,
    ensure_table_row_height,
)
from concrete_mix_designer.domain.models import CATEGORY_LABELS, ConstraintMode, MaterialCategory
from concrete_mix_designer.services.app_state import AppState
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
        ratio_row = QHBoxLayout()
        ratio_row.addWidget(QLabel("Relación agua/material cementante:"))
        ratio_row.addWidget(self.ratio_spin)
        ratio_row.addWidget(self.ratio_lock)
        ratio_row.addStretch()

        # Physical design table only. Composition percentages and admixture
        # dosage are intentionally removed and represented as visible rules.
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Candado", "Material", "Tipo", "Cantidad", "Unidad", "G.E.", "Volumen L"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        for column in (0, 3, 4, 5, 6):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)

        self.material_combo = QComboBox()
        add_button = QPushButton("Agregar componente")
        add_button.clicked.connect(self._add_component)
        remove_button = QPushButton("Eliminar seleccionado")
        remove_button.setObjectName("Danger")
        remove_button.clicked.connect(self._remove_selected)
        component_controls = QHBoxLayout()
        component_controls.addWidget(self.material_combo, 1)
        component_controls.addWidget(add_button)
        component_controls.addWidget(remove_button)

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
        constraints_header.setSectionResizeMode(6, QHeaderView.Interactive)
        constraints_header.resizeSection(6, 96)
        constraints_header.setMinimumSectionSize(54)

        add_constraint = QPushButton("Añadir relación o dosificación")
        add_constraint.clicked.connect(self._add_constraint)

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
        left_layout.addWidget(add_constraint)

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
        relation_controlled = component.uid in self.state.design.relation_controlled_uids
        lock_button = QToolButton()
        lock_button.setCheckable(True)
        lock_button.setChecked(component.locked)
        lock_button.setText("🔒" if component.locked else "🔓")
        lock_button.setToolTip("Bloquear o liberar este componente")
        lock_button.toggled.connect(partial(self._lock_changed, component.uid, lock_button))
        self.table.setCellWidget(row, 0, lock_button)

        name_item = QTableWidgetItem(component.material.name)
        name_item.setData(Qt.UserRole, component.uid)
        self.table.setItem(row, 1, name_item)
        self.table.setItem(row, 2, QTableWidgetItem(CATEGORY_LABELS[component.category]))

        quantity = ExplicitFocusDoubleSpinBox()
        quantity.setRange(0.0, 10000.0)
        quantity.setDecimals(3)
        quantity.setSingleStep(1.0)
        quantity.setKeyboardTracking(False)
        quantity.setValue(component.quantity)
        quantity.setProperty("relationControlled", relation_controlled)
        quantity.setEnabled(not relation_controlled)
        if relation_controlled:
            quantity.setToolTip(
                "Cantidad controlada automáticamente por una relación o dosificación activa."
            )
            name_item.setToolTip(quantity.toolTip())
        quantity.editingFinished.connect(
            partial(self._quantity_finished, component.uid, quantity)
        )
        self.table.setCellWidget(row, 3, quantity)
        self.table.setItem(row, 4, QTableWidgetItem(component.unit))
        self.table.setItem(
            row, 5, QTableWidgetItem(f"{component.material.specific_gravity:.3f}")
        )
        self.table.setItem(row, 6, QTableWidgetItem(f"{component.absolute_volume_l:.3f}"))
        ensure_table_row_height(self.table, row)

    def _populate_constraints(self) -> None:
        constraints = self.state.design.ratio_constraints
        self.constraints_table.setRowCount(len(constraints))
        for row, constraint in enumerate(constraints):
            numerator = self.state.design.component(constraint.numerator_uid)
            denominator = self.state.design.component(constraint.denominator_uid)

            active = QCheckBox()
            active.setChecked(constraint.enabled)
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
            delete.clicked.connect(
                lambda _checked=False, uid=constraint.uid: self.state.remove_ratio_constraint(uid)
            )
            self.constraints_table.setCellWidget(row, 6, delete)
            ensure_table_row_height(self.constraints_table, row)

    def _quantity_finished(self, uid: str, widget: ExplicitFocusDoubleSpinBox) -> None:
        if not self._refreshing:
            self.state.set_quantity(uid, widget.value())

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
